from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app

from ..extensions import db
from ..models import (
    Genre,
    Movie,
    MovieGenre,
    MovieReview,
    MovieTitle,
    RecommendationItem,
    RecommendationRun,
    UserFavoriteGenre,
    UserMovieLibrary,
)


FEATURE_VERSION = "db-hybrid-v2"
RULE_MODEL_NAME = "rules-v1"

class RecommendationUnavailable(RuntimeError):
    pass


class AIRecommendationError(RuntimeError):
    pass


@dataclass
class UserPreferenceProfile:
    favorite_genres: list[tuple[str, str, int]]
    activity_genre_weights: dict[str, float]
    known_movies: dict[int, dict[str, Any]]
    fingerprint: str


@dataclass
class Candidate:
    movie_id: Any
    tmdb_id: int
    title: str
    original_title: str
    overview: str
    release_date: str | None
    poster_url: str | None
    genre_codes: list[str]
    genre_names: list[str]
    is_wishlisted: bool = False
    watch_status: str | None = None
    base_score: float = 0.0

def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _serialize_datetime(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value else None


def _profile_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def catalog_fingerprint(movie_count: int, latest_update: datetime | None) -> str:
    return _profile_fingerprint({
        "movie_count": int(movie_count),
        "latest_updated_at": _serialize_datetime(latest_update),
    })


def should_exclude_known_movie(known: dict[str, Any]) -> bool:
    return known.get("watch_status") == "WATCHED" or bool(known.get("has_review"))


def score_candidates(candidates: list[Candidate], profile: UserPreferenceProfile) -> list[Candidate]:
    favorite_priority_weights = {1: 1.0, 2: 0.7, 3: 0.5}
    favorite_weights = {
        code: favorite_priority_weights.get(priority, 0.4)
        for code, _name, priority in profile.favorite_genres
    }
    favorite_total = sum(favorite_weights.values()) or 1.0
    activity_total = sum(profile.activity_genre_weights.values()) or 1.0
    for candidate in candidates:
        candidate_genres = set(candidate.genre_codes)
        favorite_affinity = sum(
            weight for code, weight in favorite_weights.items() if code in candidate_genres
        ) / favorite_total
        activity_affinity = sum(
            weight
            for code, weight in profile.activity_genre_weights.items()
            if code in candidate_genres
        ) / activity_total
        interest = 1.0 if candidate.is_wishlisted or candidate.watch_status == "WATCHING" else 0.0

        candidate.base_score = round(
            (favorite_affinity * 0.65)
            + (activity_affinity * 0.25)
            + (interest * 0.10),
            6,
        )

    return sorted(candidates, key=lambda candidate: candidate.base_score, reverse=True)


class OpenAIReranker:
    def __init__(self, api_key: str | None, model: str, timeout: float):
        self.api_key = (api_key or "").strip()
        self.model = model
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def rerank(
        self,
        candidates: list[Candidate],
        profile: UserPreferenceProfile,
        limit: int,
        safety_identifier: str,
    ) -> dict[int, tuple[float, str]]:
        if not self.is_configured:
            raise AIRecommendationError("OPENAI_API_KEY가 설정되지 않았습니다.")

        try:
            from openai import OpenAI
            from pydantic import BaseModel, Field

            class RankedMovie(BaseModel):
                tmdb_id: int
                ai_score: float = Field(ge=0, le=1)
                reason: str = Field(min_length=1, max_length=180)

            class RankedMovies(BaseModel):
                recommendations: list[RankedMovie]

            client = OpenAI(
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=1,
            )
            input_payload = {
                "favorite_genres": [
                    {"code": code, "name": name, "priority": priority}
                    for code, name, priority in profile.favorite_genres
                ],
                "candidates": [
                    {
                        "tmdb_id": candidate.tmdb_id,
                        "title": candidate.title,
                        "genres": candidate.genre_names,
                        "overview": candidate.overview[:600],
                        "is_wishlisted": candidate.is_wishlisted,
                        "watch_status": candidate.watch_status,
                        "rule_score": candidate.base_score,
                    }
                    for candidate in candidates
                ],
            }
            response = client.responses.parse(
                model=self.model,
                reasoning={"effort": "low"},
                store=False,
                safety_identifier=safety_identifier,
                instructions=(
                    "당신은 한국 영화 서비스의 개인화 순위 모델입니다. "
                    "입력된 후보 안에서만 사용자의 장르 취향과 활동 기록 적합도를 평가하세요. "
                    f"서로 다른 영화 최대 {limit}편을 고르고 한국어로 구체적이지만 짧은 추천 이유를 작성하세요. "
                    "입력에 없는 사실을 만들지 마세요."
                ),
                input=json.dumps(input_payload, ensure_ascii=False),
                text_format=RankedMovies,
            )
            parsed = response.output_parsed
        except Exception as exc:
            raise AIRecommendationError("OpenAI 추천 응답을 생성하지 못했습니다.") from exc

        if parsed is None or not 1 <= len(parsed.recommendations) <= limit:
            raise AIRecommendationError("OpenAI 추천 응답 개수가 올바르지 않습니다.")

        allowed_ids = {candidate.tmdb_id for candidate in candidates}
        ranked: dict[int, tuple[float, str]] = {}
        for item in parsed.recommendations:
            reason = item.reason.strip()
            if item.tmdb_id not in allowed_ids or item.tmdb_id in ranked or not reason:
                raise AIRecommendationError("OpenAI 추천 응답에 허용되지 않은 영화가 포함되었습니다.")
            ranked[item.tmdb_id] = (float(item.ai_score), reason[:180])
        return ranked


class RecommendationService:
    def __init__(self, ai: OpenAIReranker):
        self.ai = ai

    def get_cached(self, user_id: Any, limit: int) -> dict[str, Any]:
        profile = self._load_profile(user_id)
        catalog_fingerprint = self._catalog_fingerprint()
        run = self._latest_run(user_id)
        if run is None:
            return self._empty_payload()

        context = run.context or {}
        now = datetime.now(timezone.utc)
        if (
            _as_utc(run.expires_at) <= now
            or context.get("profile_fingerprint") != profile.fingerprint
            or context.get("catalog_fingerprint") != catalog_fingerprint
            or context.get("limit") != limit
        ):
            return self._empty_payload()
        return self._serialize_run(run, source="cache")

    def generate(self, user_id: Any, limit: int, force: bool = False) -> dict[str, Any]:
        profile = self._load_profile(user_id)
        catalog_fingerprint = self._catalog_fingerprint()
        if not force:
            run = self._latest_run(user_id)
            if run is not None:
                context = run.context or {}
                if (
                    _as_utc(run.expires_at) > datetime.now(timezone.utc)
                    and context.get("profile_fingerprint") == profile.fingerprint
                    and context.get("catalog_fingerprint") == catalog_fingerprint
                    and context.get("limit") == limit
                ):
                    return self._serialize_run(run, source="cache")

        candidates = self._collect_candidates(profile)

        if not candidates:
            raise RecommendationUnavailable("추천할 영화 후보를 찾지 못했습니다.")

        scored = score_candidates(candidates, profile)
        candidate_limit = current_app.config["RECOMMENDATION_CANDIDATE_LIMIT"]
        pool = scored[:candidate_limit]

        # Candidate and profile reads are complete. Release the database transaction
        # before the optional OpenAI network request and persist in a short new one.
        db.session.rollback()

        source = "rules"
        model_name = RULE_MODEL_NAME
        ai_ranked: dict[int, tuple[float, str]] = {}
        if self.ai.is_configured:
            try:
                ai_ranked = self.ai.rerank(
                    pool,
                    profile,
                    limit,
                    self._safety_identifier(user_id),
                )
                source = "ai"
                model_name = self.ai.model
            except AIRecommendationError:
                ai_ranked = {}

        ranked = []
        for candidate in pool:
            ai_value = ai_ranked.get(candidate.tmdb_id)
            final_score = (
                (candidate.base_score * 0.6) + (ai_value[0] * 0.4)
                if ai_value is not None
                else candidate.base_score * (0.6 if ai_ranked else 1.0)
            )
            ranked.append((candidate, round(final_score, 6), ai_value[1] if ai_value else None))

        selected = sorted(ranked, key=lambda row: row[1], reverse=True)[:limit]

        run = self._persist(
            user_id,
            profile,
            catalog_fingerprint,
            selected,
            source,
            model_name,
            limit,
        )
        return self._serialize_run(run, source=source)

    def _load_profile(self, user_id: Any) -> UserPreferenceProfile:
        favorite_rows = (
            db.session.query(UserFavoriteGenre, Genre)
            .join(Genre, Genre.id == UserFavoriteGenre.genre_id)
            .filter(UserFavoriteGenre.user_id == user_id)
            .order_by(UserFavoriteGenre.priority)
            .all()
        )
        favorite_genres = [
            (genre.code, genre.name, favorite.priority)
            for favorite, genre in favorite_rows
        ]

        library_rows = (
            db.session.query(UserMovieLibrary, Movie)
            .join(Movie, Movie.id == UserMovieLibrary.movie_id)
            .filter(UserMovieLibrary.user_id == user_id)
            .all()
        )
        review_rows = (
            db.session.query(MovieReview, Movie)
            .join(Movie, Movie.id == MovieReview.movie_id)
            .filter(MovieReview.user_id == user_id, MovieReview.deleted_at.is_(None))
            .all()
        )

        known_movies: dict[int, dict[str, Any]] = {}
        positive_movie_ids: set[Any] = set()
        activity_payload = []
        for library, movie in library_rows:
            if movie.tmdb_id is None:
                continue
            known_movies[int(movie.tmdb_id)] = {
                "is_wishlisted": bool(library.is_wishlisted),
                "watch_status": library.watch_status,
            }
            if library.is_wishlisted or library.watch_status == "WATCHING":
                positive_movie_ids.add(movie.id)
            activity_payload.append({
                "tmdb_id": int(movie.tmdb_id),
                "wishlisted": bool(library.is_wishlisted),
                "watch_status": library.watch_status,
                "updated_at": _serialize_datetime(library.updated_at),
            })

        review_payload = []
        for review, movie in review_rows:
            if movie.tmdb_id is None:
                continue
            known_movies.setdefault(
                int(movie.tmdb_id),
                {"is_wishlisted": False, "watch_status": None},
            )["has_review"] = True
            if review.rating_half_steps >= 8:
                positive_movie_ids.add(movie.id)
            review_payload.append({
                "tmdb_id": int(movie.tmdb_id),
                "rating_half_steps": review.rating_half_steps,
                "updated_at": _serialize_datetime(review.updated_at),
            })

        activity_genre_weights: dict[str, float] = {}
        if positive_movie_ids:
            genre_rows = (
                db.session.query(MovieGenre, Genre)
                .join(Genre, Genre.id == MovieGenre.genre_id)
                .filter(MovieGenre.movie_id.in_(positive_movie_ids))
                .all()
            )
            for _movie_genre, genre in genre_rows:
                activity_genre_weights[genre.code] = activity_genre_weights.get(genre.code, 0.0) + 1.0

        fingerprint_payload = {
            "favorite_genres": [(code, priority) for code, _name, priority in favorite_genres],
            "activity": sorted(activity_payload, key=lambda item: item["tmdb_id"]),
            "reviews": sorted(review_payload, key=lambda item: item["tmdb_id"]),
        }
        return UserPreferenceProfile(
            favorite_genres=favorite_genres,
            activity_genre_weights=activity_genre_weights,
            known_movies=known_movies,
            fingerprint=_profile_fingerprint(fingerprint_payload),
        )

    def _collect_candidates(self, profile: UserPreferenceProfile) -> list[Candidate]:
        movies = (
            Movie.query
            .filter(Movie.tmdb_id.isnot(None))
            .order_by(Movie.id)
            .all()
        )
        if not movies:
            return []

        movie_ids = [movie.id for movie in movies]
        title_rows = (
            MovieTitle.query
            .filter(
                MovieTitle.movie_id.in_(movie_ids),
                MovieTitle.locale == "ko-KR",
                MovieTitle.title_type == "PRIMARY",
            )
            .all()
        )
        titles_by_movie = {title.movie_id: title.title for title in title_rows}
        genre_rows = (
            db.session.query(MovieGenre, Genre)
            .join(Genre, Genre.id == MovieGenre.genre_id)
            .filter(MovieGenre.movie_id.in_(movie_ids))
            .all()
        )
        genres_by_movie: dict[Any, list[Genre]] = {}
        for movie_genre, genre in genre_rows:
            genres_by_movie.setdefault(movie_genre.movie_id, []).append(genre)

        candidates = []
        for movie in movies:
            tmdb_id = int(movie.tmdb_id)
            known = profile.known_movies.get(tmdb_id, {})
            if should_exclude_known_movie(known):
                continue
            genres = genres_by_movie.get(movie.id, [])
            candidates.append(Candidate(
                movie_id=movie.id,
                tmdb_id=tmdb_id,
                title=titles_by_movie.get(movie.id, movie.original_title),
                original_title=movie.original_title,
                overview=movie.overview or "",
                release_date=movie.release_date.isoformat() if movie.release_date else None,
                poster_url=movie.poster_url,
                genre_codes=[genre.code for genre in genres],
                genre_names=[genre.name for genre in genres],
                is_wishlisted=bool(known.get("is_wishlisted")),
                watch_status=known.get("watch_status"),
            ))
        return candidates

    def _catalog_fingerprint(self) -> str:
        movie_count, latest_update = (
            db.session.query(db.func.count(Movie.id), db.func.max(Movie.updated_at))
            .filter(Movie.tmdb_id.isnot(None))
            .one()
        )
        return catalog_fingerprint(int(movie_count or 0), latest_update)

    def _persist(
        self,
        user_id: Any,
        profile: UserPreferenceProfile,
        catalog_fingerprint: str,
        selected: list[tuple[Candidate, float, str | None]],
        source: str,
        model_name: str,
        limit: int,
    ) -> RecommendationRun:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=current_app.config["RECOMMENDATION_TTL_HOURS"])

        try:
            run = RecommendationRun(
                user_id=user_id,
                provider_id=None,
                recommendation_type="PERSONALIZED",
                model_name=model_name,
                feature_version=FEATURE_VERSION,
                context={
                    "source": source,
                    "profile_fingerprint": profile.fingerprint,
                    "catalog_fingerprint": catalog_fingerprint,
                    "candidate_policy": "DATABASE_ONLY",
                    "limit": limit,
                },
                generated_at=now,
                expires_at=expires_at,
            )
            db.session.add(run)
            db.session.flush()

            for rank, (candidate, score, ai_reason) in enumerate(selected, start=1):
                db.session.add(RecommendationItem(
                    run_id=run.id,
                    movie_id=candidate.movie_id,
                    rank=rank,
                    score=max(0.0, min(score, 1.0)),
                    reason_text=ai_reason or self._rule_reason(candidate, profile),
                    reason_codes={
                        "source": "ai" if ai_reason else "rules",
                        "genres": candidate.genre_names,
                        "base_score": candidate.base_score,
                    },
                ))
            db.session.commit()
            return run
        except Exception:
            db.session.rollback()
            raise

    def _rule_reason(self, candidate: Candidate, profile: UserPreferenceProfile) -> str:
        favorite_codes = {code for code, _name, _priority in profile.favorite_genres}
        matched_genres = [
            name
            for code, name in zip(candidate.genre_codes, candidate.genre_names)
            if code in favorite_codes
        ]
        parts = []
        if matched_genres:
            parts.append(f"선호 장르인 {', '.join(matched_genres[:2])}와 잘 맞아요")
        if candidate.is_wishlisted:
            parts.append("찜해 둔 관심작이에요")
        elif candidate.watch_status == "WATCHING":
            parts.append("현재 감상 중인 작품이에요")
        if not parts:
            parts.append("선호 장르와 활동 기록을 종합해 골랐어요")
        return ". ".join(parts)[:500] + ("." if not parts[-1].endswith(".") else "")

    def _latest_run(self, user_id: Any) -> RecommendationRun | None:
        return (
            RecommendationRun.query
            .filter_by(user_id=user_id, recommendation_type="PERSONALIZED")
            .order_by(RecommendationRun.generated_at.desc())
            .first()
        )

    def _serialize_run(self, run: RecommendationRun, source: str) -> dict[str, Any]:
        recommendations = []
        for item in sorted(run.items, key=lambda row: row.rank):
            movie = item.movie
            primary_title = next(
                (
                    title.title
                    for title in movie.titles
                    if title.locale == "ko-KR" and title.title_type == "PRIMARY"
                ),
                movie.original_title,
            )
            codes = item.reason_codes or {}
            recommendations.append({
                "movie_id": str(movie.id),
                "tmdb_id": int(movie.tmdb_id) if movie.tmdb_id is not None else None,
                "title": primary_title,
                "original_title": movie.original_title,
                "overview": movie.overview or "",
                "release_date": movie.release_date.isoformat() if movie.release_date else None,
                "poster_url": movie.poster_url,
                "genres": codes.get("genres", []),
                "provider_matches": codes.get("providers", []),
                "score": float(item.score),
                "reason": item.reason_text or "취향과 잘 맞는 영화예요.",
            })
        return {
            "source": source,
            "model": run.model_name,
            "generated_at": _serialize_datetime(run.generated_at),
            "expires_at": _serialize_datetime(run.expires_at),
            "recommendations": recommendations,
        }

    def _empty_payload(self) -> dict[str, Any]:
        return {
            "source": "empty",
            "model": None,
            "generated_at": None,
            "expires_at": None,
            "recommendations": [],
        }

    def _safety_identifier(self, user_id: Any) -> str:
        secret = str(current_app.config["SECRET_KEY"]).encode("utf-8")
        return hmac.new(secret, str(user_id).encode("utf-8"), hashlib.sha256).hexdigest()


def get_recommendation_service() -> RecommendationService:
    overridden = current_app.extensions.get("recommendation_service")
    if overridden is not None:
        return overridden
    return RecommendationService(
        ai=OpenAIReranker(
            current_app.config.get("OPENAI_API_KEY"),
            current_app.config["OPENAI_MODEL"],
            current_app.config["OPENAI_TIMEOUT_SECONDS"],
        ),
    )

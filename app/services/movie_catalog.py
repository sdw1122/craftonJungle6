from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from ..extensions import db
from ..models import (
    Genre,
    Movie,
    MovieCredit,
    MovieGenre,
    MovieTitle,
    OTTAvailability,
    OTTProvider,
    Person,
)
from ..ott_icons import TMDB_PROVIDER_NAME_TO_CODE
from .tmdb import TMDBClient, TMDBError, normalize_movie_detail


TMDB_GENRES: dict[int, tuple[str, str]] = {
    28: ("ACTION", "액션"),
    12: ("ADVENTURE", "모험"),
    16: ("ANIMATION", "애니메이션"),
    35: ("COMEDY", "코미디"),
    80: ("CRIME", "범죄"),
    99: ("DOCUMENTARY", "다큐멘터리"),
    18: ("DRAMA", "드라마"),
    10751: ("FAMILY", "가족"),
    14: ("FANTASY", "판타지"),
    36: ("HISTORY", "역사"),
    27: ("HORROR", "공포"),
    10402: ("MUSIC", "음악"),
    9648: ("MYSTERY", "미스터리"),
    10749: ("ROMANCE", "로맨스"),
    878: ("SF", "SF"),
    53: ("THRILLER", "스릴러"),
    10752: ("WAR", "전쟁"),
    37: ("WESTERN", "서부"),
}

class MovieCatalogSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class MovieCatalogSyncResult:
    requested: int
    now_playing_requested: int
    created: int
    updated: int
    titles_synced: int
    genre_links_synced: int


def _parse_release_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def collect_popular_movies(tmdb: TMDBClient, limit: int) -> list[dict[str, Any]]:
    return _collect_ranked_movies(
        tmdb.get_popular_movies,
        limit=limit,
        label="인기 영화",
    )


def collect_now_playing_movies(tmdb: TMDBClient) -> list[dict[str, Any]]:
    movies: dict[int, dict[str, Any]] = {}
    page = 1
    total_pages = 500

    while page <= min(total_pages, 500):
        result = tmdb.get_now_playing_movies(page)
        total_pages = min(int(result.get("total_pages") or 0), 500)
        page_results = result.get("results") or []
        if not page_results:
            break
        for movie in page_results:
            tmdb_id = movie.get("id")
            if tmdb_id is None or movie.get("adult") is True:
                continue
            movies.setdefault(int(tmdb_id), movie)
        page += 1

    if not movies:
        raise MovieCatalogSyncError("TMDB 한국 현재 상영작을 확보하지 못했습니다.")
    return list(movies.values())


def _collect_ranked_movies(fetch_page, *, limit: int, label: str) -> list[dict[str, Any]]:
    movies: dict[int, dict[str, Any]] = {}
    page = 1
    total_pages = 500

    while len(movies) < limit and page <= min(total_pages, 500):
        result = fetch_page(page)
        total_pages = min(int(result.get("total_pages") or 0), 500)
        page_results = result.get("results") or []
        if not page_results:
            break
        for movie in page_results:
            tmdb_id = movie.get("id")
            if tmdb_id is None or movie.get("adult") is True:
                continue
            movies.setdefault(int(tmdb_id), movie)
            if len(movies) == limit:
                break
        page += 1

    if len(movies) != limit:
        raise MovieCatalogSyncError(
            f"TMDB {label} {limit}편을 확보하지 못했습니다. 수집 결과: {len(movies)}편"
        )
    return list(movies.values())


class MovieCatalogSyncService:
    def __init__(self, tmdb: TMDBClient):
        self.tmdb = tmdb

    def sync_popular(self, limit: int = 100) -> MovieCatalogSyncResult:
        try:
            popular_movies = collect_popular_movies(self.tmdb, limit)
            now_playing_movies = collect_now_playing_movies(self.tmdb)
            popular_ranks = {
                int(summary["id"]): rank
                for rank, summary in enumerate(popular_movies, start=1)
            }
            now_playing_ranks = {
                int(summary["id"]): rank
                for rank, summary in enumerate(now_playing_movies, start=1)
            }
            movie_ids = list(popular_ranks)
            movie_ids.extend(
                tmdb_id for tmdb_id in now_playing_ranks if tmdb_id not in popular_ranks
            )
            movies = []
            for tmdb_id in movie_ids:
                detail = self.tmdb.get_movie(tmdb_id)
                providers = self.tmdb.get_watch_providers(tmdb_id)
                movies.append(normalize_movie_detail(detail, providers))
        except TMDBError as exc:
            raise MovieCatalogSyncError(exc.message) from exc

        now = datetime.now(timezone.utc)
        today = date.today()
        genres_by_code = {genre.code: genre for genre in Genre.query.all()}
        providers_by_code = {provider.code: provider for provider in OTTProvider.query.all()}
        created = 0
        updated = 0
        titles_synced = 0
        genre_links_synced = 0

        try:
            Movie.query.filter(Movie.popular_rank.isnot(None)).update(
                {Movie.popular_rank: None},
                synchronize_session=False,
            )
            Movie.query.filter(Movie.now_playing_rank.isnot(None)).update(
                {Movie.now_playing_rank: None},
                synchronize_session=False,
            )

            for payload in movies:
                tmdb_id = int(payload["tmdb_id"])
                movie = Movie.query.filter_by(tmdb_id=tmdb_id).first()
                if movie is None:
                    movie = Movie(
                        tmdb_id=tmdb_id,
                        original_title=(
                            payload.get("original_title")
                            or payload.get("title")
                            or "제목 없음"
                        ).strip(),
                    )
                    db.session.add(movie)
                    db.session.flush()
                    created += 1
                else:
                    updated += 1

                movie.original_title = (
                    payload.get("original_title")
                    or payload.get("title")
                    or "제목 없음"
                ).strip()
                movie.overview = (payload.get("overview") or "").strip() or None
                movie.release_date = _parse_release_date(payload.get("release_date"))
                movie.runtime_minutes = payload.get("runtime_minutes") or None
                movie.original_language = payload.get("original_language") or None
                movie.poster_url = payload.get("poster_url")
                movie.backdrop_url = payload.get("backdrop_url")
                movie.popular_rank = popular_ranks.get(tmdb_id)
                movie.now_playing_rank = now_playing_ranks.get(tmdb_id)
                movie.updated_at = now

                localized_title = (
                    payload.get("title")
                    or payload.get("original_title")
                    or "제목 없음"
                ).strip()
                title = MovieTitle.query.filter_by(
                    movie_id=movie.id,
                    locale="ko-KR",
                    title_type="PRIMARY",
                ).first()
                if title is None:
                    db.session.add(MovieTitle(
                        movie_id=movie.id,
                        locale="ko-KR",
                        title=localized_title,
                        title_type="PRIMARY",
                    ))
                else:
                    title.title = localized_title
                titles_synced += 1

                MovieGenre.query.filter_by(movie_id=movie.id).delete(synchronize_session=False)
                for genre_payload in payload.get("genres") or []:
                    genre_info = TMDB_GENRES.get(int(genre_payload["tmdb_id"]))
                    if genre_info is None:
                        continue
                    genre = genres_by_code.get(genre_info[0])
                    if genre is None:
                        continue
                    db.session.add(MovieGenre(movie_id=movie.id, genre_id=genre.id))
                    genre_links_synced += 1

                MovieCredit.query.filter_by(movie_id=movie.id).delete(synchronize_session=False)
                credit_payloads = [
                    ("DIRECTOR", director)
                    for director in payload.get("directors") or []
                ] + [
                    ("ACTOR", actor)
                    for actor in payload.get("cast") or []
                ]
                for credit_type, person_payload in credit_payloads:
                    person_tmdb_id = int(person_payload["tmdb_id"])
                    person = Person.query.filter_by(tmdb_id=person_tmdb_id).first()
                    if person is None:
                        person = Person(
                            tmdb_id=person_tmdb_id,
                            primary_name=person_payload["name"],
                        )
                        db.session.add(person)
                        db.session.flush()
                    else:
                        person.primary_name = person_payload["name"]
                    db.session.add(MovieCredit(
                        movie_id=movie.id,
                        person_id=person.id,
                        credit_type=credit_type,
                        character_name=person_payload.get("character_name"),
                        billing_order=person_payload.get("billing_order"),
                    ))

                OTTAvailability.query.filter_by(movie_id=movie.id).delete(
                    synchronize_session=False
                )
                for availability in payload.get("watch_providers") or []:
                    provider_code = TMDB_PROVIDER_NAME_TO_CODE.get(availability.get("name"))
                    provider = providers_by_code.get(provider_code)
                    offer_type = availability.get("offer_type")
                    if provider is None or offer_type not in {"SUBSCRIPTION", "FREE", "RENT", "BUY"}:
                        continue
                    db.session.add(OTTAvailability(
                        movie_id=movie.id,
                        provider_id=provider.id,
                        region_code="KR",
                        offer_type=offer_type,
                        available_from=today,
                        content_url=payload.get("watch_provider_link"),
                        source="TMDB",
                        source_updated_at=now,
                        last_checked_at=now,
                    ))

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return MovieCatalogSyncResult(
            requested=limit,
            now_playing_requested=len(now_playing_movies),
            created=created,
            updated=updated,
            titles_synced=titles_synced,
            genre_links_synced=genre_links_synced,
        )


def sync_popular_movie_catalog(
    *,
    access_token: str | None,
    limit: int = 100,
) -> MovieCatalogSyncResult:
    return MovieCatalogSyncService(TMDBClient(access_token)).sync_popular(limit)

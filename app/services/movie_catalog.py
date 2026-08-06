from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from ..extensions import db
from ..models import Genre, Movie, MovieGenre, MovieTitle
from .tmdb import TMDBClient, TMDBError


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
    movies: dict[int, dict[str, Any]] = {}
    page = 1
    total_pages = 500

    while len(movies) < limit and page <= min(total_pages, 500):
        result = tmdb.get_popular_movies(page)
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
            f"TMDB 인기 영화 {limit}편을 확보하지 못했습니다. 수집 결과: {len(movies)}편"
        )
    return list(movies.values())


class MovieCatalogSyncService:
    def __init__(self, tmdb: TMDBClient):
        self.tmdb = tmdb

    def sync_popular(self, limit: int = 100) -> MovieCatalogSyncResult:
        try:
            movies = collect_popular_movies(self.tmdb, limit)
        except TMDBError as exc:
            raise MovieCatalogSyncError(exc.message) from exc

        now = datetime.now(timezone.utc)
        genres_by_code = {genre.code: genre for genre in Genre.query.all()}
        created = 0
        updated = 0
        titles_synced = 0
        genre_links_synced = 0

        try:
            for payload in movies:
                tmdb_id = int(payload["id"])
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
                movie.original_language = payload.get("original_language") or None
                movie.poster_url = TMDBClient.image_url(payload.get("poster_path"))
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
                for tmdb_genre_id in payload.get("genre_ids") or []:
                    genre_info = TMDB_GENRES.get(int(tmdb_genre_id))
                    if genre_info is None:
                        continue
                    genre = genres_by_code.get(genre_info[0])
                    if genre is None:
                        continue
                    db.session.add(MovieGenre(movie_id=movie.id, genre_id=genre.id))
                    genre_links_synced += 1

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return MovieCatalogSyncResult(
            requested=limit,
            created=created,
            updated=updated,
            titles_synced=titles_synced,
            genre_links_synced=genre_links_synced,
        )

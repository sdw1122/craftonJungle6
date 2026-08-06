from datetime import date, datetime

from .extensions import db
from .models import Movie


def _parse_release_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_or_create_movie(
    *,
    tmdb_id: int,
    title: str | None = None,
    overview: str | None = None,
    release_date: str | None = None,
    poster_url: str | None = None,
) -> Movie:
    """tmdb_id로 로컬 movies 테이블을 조회하고, 없으면 새로 만들어 반환한다.

    영화 데이터 자체(장르/출연진 등)는 C 담당 TMDB 동기화 작업 범위라,
    여기서는 찜/리뷰가 참조할 수 있는 최소한의 movies 행만 보장한다.
    """
    movie = Movie.query.filter_by(tmdb_id=tmdb_id).first()
    if movie is not None:
        return movie

    movie = Movie(
        tmdb_id=tmdb_id,
        original_title=title or f"TMDB #{tmdb_id}",
        overview=overview,
        release_date=_parse_release_date(release_date),
        poster_url=poster_url,
    )
    db.session.add(movie)
    db.session.flush()
    return movie

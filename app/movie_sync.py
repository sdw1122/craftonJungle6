from datetime import date, datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from .extensions import db
from .models import Movie, OTTAvailability, OTTProvider
from .ott_icons import TMDB_PROVIDER_NAME_TO_CODE


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


def sync_ott_availability(movie: Movie, watch_providers: list[dict]) -> None:
    """영화 상세페이지에서 받아온 TMDB watch-provider 정보를 ott_availabilities에 반영한다.

    우리가 아는 7개 OTT(ott_providers)에 매칭되는 것만 저장하고,
    이미 저장된 조합은 last_checked_at만 갱신한다.
    """
    today = date.today()

    for entry in watch_providers:
        code = TMDB_PROVIDER_NAME_TO_CODE.get(entry.get("name"))
        if code is None:
            continue

        provider = OTTProvider.query.filter_by(code=code).first()
        if provider is None:
            continue

        offer_type = entry.get("offer_type")
        existing = OTTAvailability.query.filter_by(
            movie_id=movie.id,
            provider_id=provider.id,
            region_code="KR",
            offer_type=offer_type,
        ).first()

        if existing is not None:
            existing.last_checked_at = datetime.now(timezone.utc)
        else:
            db.session.add(OTTAvailability(
                movie_id=movie.id,
                provider_id=provider.id,
                region_code="KR",
                offer_type=offer_type,
                available_from=today,
            ))

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise

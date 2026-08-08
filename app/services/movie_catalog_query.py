from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from sqlalchemy import exists, or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import (
    Movie,
    MovieCredit,
    MovieGenre,
    MovieReview,
    MovieTitle,
    OTTAvailability,
    OTTProvider,
    Person,
    UserFavoriteGenre,
    UserMovieLibrary,
    UserOTTSubscription,
)


CATALOG_PAGE_SIZE = 20


@dataclass(frozen=True)
class MoviePage:
    movies: list[dict]
    page: int
    total_pages: int
    total_results: int


@dataclass(frozen=True)
class MovieDetailRecord:
    movie: Movie
    payload: dict


def _localized_title(movie: Movie) -> str:
    primary = next(
        (
            title.title
            for title in movie.titles
            if title.locale == "ko-KR" and title.title_type == "PRIMARY"
        ),
        None,
    )
    return primary or movie.original_title


def serialize_movie_summary(movie: Movie) -> dict:
    return {
        "tmdb_id": movie.tmdb_id,
        "title": _localized_title(movie),
        "original_title": movie.original_title,
        "overview": movie.overview,
        "release_date": movie.release_date.isoformat() if movie.release_date else None,
        "poster_url": movie.poster_url,
        "backdrop_url": movie.backdrop_url,
    }


def _serialize_ranked_movies(movies: list[Movie]) -> list[dict]:
    if not movies:
        return []

    movie_ids = [movie.id for movie in movies]
    provider_rows = (
        db.session.query(OTTAvailability.movie_id, OTTProvider)
        .join(OTTProvider, OTTProvider.id == OTTAvailability.provider_id)
        .filter(
            OTTAvailability.movie_id.in_(movie_ids),
            OTTAvailability.region_code == "KR",
            OTTProvider.is_active.is_(True),
        )
        .order_by(OTTProvider.id)
        .all()
    )
    providers_by_movie: dict = {}
    seen: dict = {}
    for movie_id, provider in provider_rows:
        movie_seen = seen.setdefault(movie_id, set())
        if provider.id in movie_seen:
            continue
        movie_seen.add(provider.id)
        providers_by_movie.setdefault(movie_id, []).append({
            "id": provider.id,
            "code": provider.code,
            "name": provider.name,
        })

    results = []
    for movie in movies:
        payload = serialize_movie_summary(movie)
        payload["popular_rank"] = movie.popular_rank
        payload["now_playing_rank"] = movie.now_playing_rank
        payload["providers"] = providers_by_movie.get(movie.id, [])
        results.append(payload)
    return results


def list_ranked_movies(*, limit: int = 3, provider_ids: list[int] | None = None) -> list[dict]:
    query = Movie.query.filter(
        Movie.tmdb_id.isnot(None),
        Movie.popular_rank.isnot(None),
    )
    if provider_ids:
        available_movie_ids = (
            db.select(OTTAvailability.movie_id)
            .where(
                OTTAvailability.provider_id.in_(provider_ids),
                OTTAvailability.region_code == "KR",
            )
        )
        query = query.filter(Movie.id.in_(available_movie_ids))

    movies = (
        query
        .options(selectinload(Movie.titles))
        .order_by(Movie.popular_rank, Movie.tmdb_id)
        .limit(limit)
        .all()
    )
    return _serialize_ranked_movies(movies)


def list_now_playing_movies(*, limit: int = 50) -> list[dict]:
    movies = (
        Movie.query
        .filter(
            Movie.tmdb_id.isnot(None),
            Movie.now_playing_rank.isnot(None),
        )
        .options(selectinload(Movie.titles))
        .order_by(Movie.now_playing_rank, Movie.tmdb_id)
        .limit(limit)
        .all()
    )
    return _serialize_ranked_movies(movies)


def list_random_movies(*, limit: int = 50) -> list[dict]:
    movies = (
        Movie.query
        .filter(Movie.tmdb_id.isnot(None))
        .options(selectinload(Movie.titles))
        .order_by(db.func.random())
        .limit(limit)
        .all()
    )
    return _serialize_ranked_movies(movies)


def active_subscription_provider_ids(user_id) -> list[int]:
    return [
        subscription.provider_id
        for subscription in (
            UserOTTSubscription.query
            .filter_by(user_id=user_id, ended_at=None)
            .order_by(UserOTTSubscription.provider_id)
            .all()
        )
    ]


def list_active_ott_providers() -> list[OTTProvider]:
    return (
        OTTProvider.query
        .filter_by(is_active=True)
        .order_by(OTTProvider.id)
        .all()
    )


def list_personalized_movies(*, user_id, limit: int = 3) -> list[dict]:
    candidates = (
        Movie.query
        .filter(
            Movie.tmdb_id.isnot(None),
            Movie.popular_rank.isnot(None),
        )
        .options(selectinload(Movie.titles))
        .order_by(Movie.popular_rank, Movie.tmdb_id)
        .limit(150)
        .all()
    )
    if not candidates:
        return []

    movie_ids = [movie.id for movie in candidates]
    favorite_rows = (
        UserFavoriteGenre.query
        .filter_by(user_id=user_id)
        .order_by(UserFavoriteGenre.priority)
        .all()
    )
    genre_weights = {
        favorite.genre_id: 4 - favorite.priority
        for favorite in favorite_rows
    }
    genre_rows = (
        MovieGenre.query
        .filter(MovieGenre.movie_id.in_(movie_ids))
        .all()
    )
    score_by_movie: dict = {}
    for genre_link in genre_rows:
        score_by_movie[genre_link.movie_id] = (
            score_by_movie.get(genre_link.movie_id, 0)
            + genre_weights.get(genre_link.genre_id, 0)
        )

    watched_ids = {
        entry.movie_id
        for entry in (
            UserMovieLibrary.query
            .filter(
                UserMovieLibrary.user_id == user_id,
                UserMovieLibrary.watch_status == "WATCHED",
                UserMovieLibrary.movie_id.in_(movie_ids),
            )
            .all()
        )
    }
    reviewed_ids = {
        review.movie_id
        for review in (
            MovieReview.query
            .filter(
                MovieReview.user_id == user_id,
                MovieReview.deleted_at.is_(None),
                MovieReview.movie_id.in_(movie_ids),
            )
            .all()
        )
    }
    unseen = [
        movie for movie in candidates
        if movie.id not in watched_ids and movie.id not in reviewed_ids
    ]
    unseen.sort(key=lambda movie: (
        -score_by_movie.get(movie.id, 0),
        movie.popular_rank or 9999,
        movie.tmdb_id,
    ))
    return _serialize_ranked_movies(unseen[:limit])


def list_wishlisted_movies(*, user_id, limit: int = 12) -> list[dict]:
    movies = (
        Movie.query
        .join(UserMovieLibrary, UserMovieLibrary.movie_id == Movie.id)
        .filter(
            Movie.tmdb_id.isnot(None),
            UserMovieLibrary.user_id == user_id,
            UserMovieLibrary.is_wishlisted.is_(True),
        )
        .options(selectinload(Movie.titles))
        .order_by(
            UserMovieLibrary.updated_at.desc().nullslast(),
            Movie.popular_rank.asc().nullslast(),
            Movie.tmdb_id,
        )
        .limit(limit)
        .all()
    )
    return _serialize_ranked_movies(movies)


def wishlisted_tmdb_ids(*, user_id) -> set[int]:
    rows = (
        db.session.query(Movie.tmdb_id)
        .join(UserMovieLibrary, UserMovieLibrary.movie_id == Movie.id)
        .filter(
            Movie.tmdb_id.isnot(None),
            UserMovieLibrary.user_id == user_id,
            UserMovieLibrary.is_wishlisted.is_(True),
        )
        .all()
    )
    return {tmdb_id for (tmdb_id,) in rows}


def list_ott_rankings(*, limit: int = 3) -> list[dict]:
    providers = (
        OTTProvider.query
        .filter_by(is_active=True)
        .order_by(OTTProvider.id)
        .all()
    )
    return [
        {
            "provider": provider,
            "movies": list_ranked_movies(limit=limit, provider_ids=[provider.id]),
        }
        for provider in providers
    ]


def list_catalog_movies(*, page: int = 1, query: str = "") -> MoviePage:
    catalog_query = Movie.query.filter(Movie.tmdb_id.isnot(None))
    if query:
        search_term = f"%{query}%"
        catalog_query = catalog_query.filter(
            or_(
                Movie.original_title.ilike(search_term),
                Movie.titles.any(MovieTitle.title.ilike(search_term)),
                exists().where(
                    MovieCredit.movie_id == Movie.id,
                    MovieCredit.person_id == Person.id,
                    Person.primary_name.ilike(search_term),
                ),
            )
        ).order_by(Movie.release_date.desc().nullslast(), Movie.tmdb_id)
    else:
        catalog_query = catalog_query.filter(Movie.popular_rank.isnot(None)).order_by(
            Movie.popular_rank,
            Movie.tmdb_id,
        )

    total_results = catalog_query.count()
    total_pages = ceil(total_results / CATALOG_PAGE_SIZE) if total_results else 0
    movies = (
        catalog_query
        .options(selectinload(Movie.titles))
        .offset((page - 1) * CATALOG_PAGE_SIZE)
        .limit(CATALOG_PAGE_SIZE)
        .all()
    )
    return MoviePage(
        movies=[serialize_movie_summary(movie) for movie in movies],
        page=page,
        total_pages=total_pages,
        total_results=total_results,
    )


def get_catalog_movie_record(tmdb_id: int) -> MovieDetailRecord | None:
    movie = (
        Movie.query
        .options(selectinload(Movie.titles))
        .filter_by(tmdb_id=tmdb_id)
        .first()
    )
    if movie is None:
        return None

    genre_links = (
        MovieGenre.query
        .filter_by(movie_id=movie.id)
        .join(MovieGenre.genre)
        .order_by(MovieGenre.genre_id)
        .all()
    )
    credits = (
        MovieCredit.query
        .filter_by(movie_id=movie.id)
        .join(MovieCredit.person)
        .order_by(MovieCredit.credit_type, MovieCredit.billing_order.nullslast(), MovieCredit.id)
        .all()
    )
    availability = (
        OTTAvailability.query
        .filter_by(movie_id=movie.id, region_code="KR")
        .join(OTTAvailability.provider)
        .order_by(OTTAvailability.offer_type, OTTAvailability.provider_id)
        .all()
    )

    directors = [
        {"tmdb_id": credit.person.tmdb_id, "name": credit.person.primary_name}
        for credit in credits
        if credit.credit_type == "DIRECTOR"
    ]
    cast = [
        {
            "tmdb_id": credit.person.tmdb_id,
            "name": credit.person.primary_name,
            "character_name": credit.character_name,
            "billing_order": credit.billing_order,
        }
        for credit in credits
        if credit.credit_type == "ACTOR"
    ]
    watch_providers = [
        {
            "name": item.provider.name,
            "code": item.provider.code,
            "offer_type": item.offer_type,
            "content_url": item.content_url,
        }
        for item in availability
    ]
    if movie.now_playing_rank is not None:
        watch_providers.insert(0, {
            "name": "박스오피스",
            "code": "BOX_OFFICE",
            "offer_type": "THEATRICAL",
            "content_url": f"https://www.themoviedb.org/movie/{movie.tmdb_id}?language=ko-KR",
        })

    payload = {
        **serialize_movie_summary(movie),
        "runtime_minutes": movie.runtime_minutes,
        "original_language": movie.original_language,
        "genres": [
            {"code": link.genre.code, "name": link.genre.name}
            for link in genre_links
        ],
        "directors": directors,
        "cast": cast,
        "now_playing_rank": movie.now_playing_rank,
        "watch_providers": watch_providers,
        "watch_provider_link": next(
            (item.content_url for item in availability if item.content_url),
            None,
        ),
    }
    return MovieDetailRecord(movie=movie, payload=payload)


def get_catalog_movie(tmdb_id: int) -> dict | None:
    record = get_catalog_movie_record(tmdb_id)
    return record.payload if record else None

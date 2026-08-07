from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from sqlalchemy import exists, or_
from sqlalchemy.orm import selectinload

from ..models import (
    Movie,
    MovieCredit,
    MovieGenre,
    MovieTitle,
    OTTAvailability,
    Person,
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
    }


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
            "offer_type": item.offer_type,
        }
        for item in availability
    ]

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

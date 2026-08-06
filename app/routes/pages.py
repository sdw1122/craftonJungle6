from flask import Blueprint, render_template, request

from movie_app.services.tmdb import (
    TMDBError,
    get_tmdb_client,
    normalize_movie_detail,
    normalize_search_movie,
)


pages_blueprint = Blueprint("pages", __name__)


@pages_blueprint.get("/")
def index():
    query = request.args.get("query", "").strip()
    page = request.args.get("page", default=1, type=int)

    if page is None or page < 1 or page > 500:
        return render_template(
            "index.html",
            movies=[],
            query=query,
            page=1,
            total_pages=0,
            total_results=0,
            error_message="page는 1부터 500 사이여야 합니다.",
        ), 400

    tmdb = get_tmdb_client()
    try:
        result = (
            tmdb.search_movies(query, page)
            if query
            else tmdb.get_popular_movies(page)
        )
    except TMDBError as exc:
        return render_template(
            "index.html",
            movies=[],
            query=query,
            page=page,
            total_pages=0,
            total_results=0,
            error_message=exc.message,
        ), exc.status_code

    return render_template(
        "index.html",
        movies=[
            normalize_search_movie(movie)
            for movie in result.get("results", [])
        ],
        query=query,
        page=result.get("page", page),
        total_pages=min(result.get("total_pages", 0), 500),
        total_results=result.get("total_results", 0),
        error_message=None,
    )


@pages_blueprint.get("/movies/<int:tmdb_id>")
def movie_detail(tmdb_id: int):
    tmdb = get_tmdb_client()
    try:
        movie = tmdb.get_movie(tmdb_id)
        providers = tmdb.get_watch_providers(tmdb_id)
    except TMDBError as exc:
        return render_template(
            "error.html",
            status_code=exc.status_code,
            message=exc.message,
        ), exc.status_code

    return render_template(
        "movie_detail.html",
        movie=normalize_movie_detail(movie, providers),
    )

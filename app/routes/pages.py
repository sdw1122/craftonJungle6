from flask import Blueprint, render_template, request
from flask_login import current_user

from ..models import MovieReview, UserMovieLibrary
from ..services.movie_catalog_query import get_catalog_movie_record, list_catalog_movies


pages_blueprint = Blueprint("pages", __name__)


@pages_blueprint.get("/")
def index():
    query = request.args.get("query", "").strip()
    page = request.args.get("page", default=1, type=int)

    if page is None or page < 1 or page > 500:
        return render_template(
            "movies/index.html",
            movies=[],
            query=query,
            page=1,
            total_pages=0,
            total_results=0,
            error_message="page는 1부터 500 사이여야 합니다.",
        ), 400

    result = list_catalog_movies(page=page, query=query)

    return render_template(
        "movies/index.html",
        movies=result.movies,
        query=query,
        page=result.page,
        total_pages=result.total_pages,
        total_results=result.total_results,
        error_message=None,
    )


@pages_blueprint.get("/movies/<int:tmdb_id>")
def movie_detail(tmdb_id: int):
    detail = get_catalog_movie_record(tmdb_id)
    if detail is None:
        return render_template(
            "movies/error.html",
            status_code=404,
            message="동기화된 영화 정보를 찾을 수 없습니다.",
        ), 404

    normalized = detail.payload
    local_movie = detail.movie

    reviews = (
        MovieReview.query
        .filter_by(movie_id=local_movie.id)
        .filter(MovieReview.deleted_at.is_(None))
        .order_by(MovieReview.created_at.desc())
        .all()
    )

    library_status = None
    my_review = None
    if current_user.is_authenticated:
        entry = UserMovieLibrary.query.filter_by(
            user_id=current_user.id, movie_id=local_movie.id
        ).first()
        if entry is not None:
            library_status = {
                "is_wishlisted": entry.is_wishlisted,
                "watch_status": entry.watch_status,
            }
        review = next((r for r in reviews if r.user_id == current_user.id), None)
        if review is not None:
            my_review = {
                "rating": review.rating,
                "content": review.content,
                "contains_spoiler": review.contains_spoiler,
            }

    return render_template(
        "movies/movie_detail.html",
        movie=normalized,
        library_status=library_status,
        my_review=my_review,
        reviews=reviews,
    )

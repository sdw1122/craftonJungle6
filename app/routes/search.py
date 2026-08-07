from flask import Blueprint, render_template, request
from flask_login import current_user

from ..services.movie_catalog_query import (
    list_catalog_movies,
    list_ranked_movies,
    wishlisted_tmdb_ids,
)


search_bp = Blueprint("search", __name__)


@search_bp.get("/search")
def search_page():
    query = request.args.get("query", "").strip()
    page = request.args.get("page", default=1, type=int)

    if page is None or page < 1 or page > 500:
        return render_template(
            "search.html",
            movies=[],
            query=query,
            page=1,
            total_pages=0,
            total_results=0,
            searched=bool(query),
            wishlisted_movie_ids=set(),
            error_message="page는 1부터 500 사이여야 합니다.",
        ), 400

    wishlisted_movie_ids = set()
    if current_user.is_authenticated:
        user_id = getattr(current_user, "id", None) or current_user.get_id()
        wishlisted_movie_ids = wishlisted_tmdb_ids(user_id=user_id)

    if not query:
        return render_template(
            "search.html",
            movies=list_ranked_movies(limit=50),
            query="",
            page=1,
            total_pages=0,
            total_results=0,
            searched=False,
            wishlisted_movie_ids=wishlisted_movie_ids,
            error_message=None,
        )

    result = list_catalog_movies(page=page, query=query)
    return render_template(
        "search.html",
        movies=result.movies,
        query=query,
        page=result.page,
        total_pages=result.total_pages,
        total_results=result.total_results,
        searched=True,
        wishlisted_movie_ids=wishlisted_movie_ids,
        error_message=None,
    )

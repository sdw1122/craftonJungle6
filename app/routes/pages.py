from flask import Blueprint, render_template, request
from flask_login import current_user

from ..models import MovieReview, UserMovieLibrary
from ..movie_sync import get_or_create_movie, sync_ott_availability
from ..services.tmdb import (
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
            "movies/index.html",
            movies=[],
            query=query,
            page=1,
            total_pages=0,
            total_results=0,
            error_message="page는 1부터 500 사이여야 합니다.",
        ), 400

    tmdb = get_tmdb_client()
    try:
        if query:
            # 1차 시도: 영화 제목으로 먼저 검색
            result = tmdb.search_movies(query, page)
            
            # 2차 시도: 만약 영화 제목 검색 결과가 0개라면
            # 사용자가 입력한 것이 배우/감독 이름일 수 있으므로 인물 검색 로직을 발동
            if not result.get("results"):
                result = tmdb.search_by_person(query, page)
        else:
            # 검색어가 없으면 평소처럼 인기 영화를 가져옴
            result = tmdb.get_popular_movies(page)
            
    except TMDBError as exc:
        return render_template(
            "movies/index.html",
            movies=[],
            query=query,
            page=page,
            total_pages=0,
            total_results=0,
            error_message=exc.message,
        ), exc.status_code

    return render_template(
        "movies/index.html",
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
            "movies/error.html",
            status_code=exc.status_code,
            message=exc.message,
        ), exc.status_code

    normalized = normalize_movie_detail(movie, providers)

    local_movie = get_or_create_movie(
        tmdb_id=tmdb_id,
        title=normalized.get("title"),
        overview=normalized.get("overview"),
        release_date=normalized.get("release_date"),
        poster_url=normalized.get("poster_url"),
    )
    sync_ott_availability(local_movie, normalized.get("watch_providers") or [])

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

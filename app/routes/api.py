from flask import Blueprint, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..services.tmdb import (
    TMDBError,
    get_tmdb_client,
    normalize_movie_detail,
    normalize_search_movie,
)


api_blueprint = Blueprint("api", __name__, url_prefix="/api")


def database_is_ready() -> bool:
    try:
        db.session.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        db.session.rollback()
        return False


@api_blueprint.get("/hello/<name>")
def hello(name: str):
    return jsonify({"message": f"안녕하세요, {name}!"})


@api_blueprint.get("/health")
def health():
    database_ready = database_is_ready()
    tmdb = get_tmdb_client()
    return jsonify({
        "status": "ok" if database_ready else "error",
        "database": "connected" if database_ready else "disconnected",
        "tmdb": "configured" if tmdb.is_configured else "not_configured",
    }), 200 if database_ready else 503


@api_blueprint.get("/tmdb/movies/search")
def search_tmdb_movies():
    query = request.args.get("query", "").strip()
    page = request.args.get("page", default=1, type=int)

    if not query:
        return jsonify({"message": "검색어를 입력해 주세요."}), 400
    if page is None or page < 1 or page > 500:
        return jsonify({"message": "page는 1부터 500 사이여야 합니다."}), 400

    try:
        result = get_tmdb_client().search_movies(query, page)
    except TMDBError as exc:
        return jsonify({"message": exc.message}), exc.status_code

    return jsonify({
        "page": result.get("page", page),
        "total_pages": result.get("total_pages", 0),
        "total_results": result.get("total_results", 0),
        "movies": [
            normalize_search_movie(movie)
            for movie in result.get("results", [])
        ],
    })


@api_blueprint.get("/tmdb/movies/<int:tmdb_id>")
def get_tmdb_movie(tmdb_id: int):
    tmdb = get_tmdb_client()
    try:
        movie = tmdb.get_movie(tmdb_id)
        providers = tmdb.get_watch_providers(tmdb_id)
    except TMDBError as exc:
        return jsonify({"message": exc.message}), exc.status_code

    return jsonify(normalize_movie_detail(movie, providers))

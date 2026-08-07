from flask import Blueprint, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..services.movie_catalog_query import get_catalog_movie, list_catalog_movies


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
    return jsonify({
        "status": "ok" if database_ready else "error",
        "database": "connected" if database_ready else "disconnected",
    }), 200 if database_ready else 503


@api_blueprint.get("/movies/search")
@api_blueprint.get("/tmdb/movies/search")
def search_movies():
    query = request.args.get("query", "").strip()
    page = request.args.get("page", default=1, type=int)

    if not query:
        return jsonify({"message": "검색어를 입력해 주세요."}), 400
    if page is None or page < 1 or page > 500:
        return jsonify({"message": "page는 1부터 500 사이여야 합니다."}), 400

    result = list_catalog_movies(page=page, query=query)

    return jsonify({
        "page": result.page,
        "total_pages": result.total_pages,
        "total_results": result.total_results,
        "movies": result.movies,
    })


@api_blueprint.get("/movies/<int:tmdb_id>")
@api_blueprint.get("/tmdb/movies/<int:tmdb_id>")
def get_movie(tmdb_id: int):
    movie = get_catalog_movie(tmdb_id)
    if movie is None:
        return jsonify({"message": "동기화된 영화 정보를 찾을 수 없습니다."}), 404
    return jsonify(movie)

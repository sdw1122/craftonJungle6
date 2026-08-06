import os

from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import URL, text
from sqlalchemy.exc import SQLAlchemyError

from tmdb_client import (
    TMDBClient,
    TMDBError,
    normalize_movie_detail,
    normalize_search_movie,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
    "postgresql+psycopg",
    username=os.getenv("DB_USER", "flask_user"),
    password=os.getenv("DB_PASSWORD", "flask_password"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("DB_NAME", "flask_app"),
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
tmdb = TMDBClient(os.getenv("TMDB_ACCESS_TOKEN"))


def database_is_ready() -> bool:
    try:
        db.session.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        db.session.rollback()
        return False


@app.route("/")
def index():
    return render_template("index.html", database_ready=database_is_ready())


@app.route("/hello/<name>")
def hello(name: str):
    return jsonify({
        "message": f"안녕하세요, {name}!"
    })


@app.route("/health")
def health():
    database_ready = database_is_ready()
    return jsonify({
        "status": "ok" if database_ready else "error",
        "database": "connected" if database_ready else "disconnected",
        "tmdb": "configured" if tmdb.is_configured else "not_configured",
    }), 200 if database_ready else 503


@app.get("/api/tmdb/movies/search")
def search_tmdb_movies():
    query = request.args.get("query", "").strip()
    page = request.args.get("page", default=1, type=int)

    if not query:
        return jsonify({"message": "검색어를 입력해 주세요."}), 400
    if page is None or page < 1 or page > 500:
        return jsonify({"message": "page는 1부터 500 사이여야 합니다."}), 400

    try:
        result = tmdb.search_movies(query, page)
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


@app.get("/api/tmdb/movies/<int:tmdb_id>")
def get_tmdb_movie(tmdb_id: int):
    try:
        movie = tmdb.get_movie(tmdb_id)
        providers = tmdb.get_watch_providers(tmdb_id)
    except TMDBError as exc:
        return jsonify({"message": exc.message}), exc.status_code

    return jsonify(normalize_movie_detail(movie, providers))

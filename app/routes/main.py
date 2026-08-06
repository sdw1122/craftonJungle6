from flask import Blueprint, jsonify, render_template
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db

main_bp = Blueprint("main", __name__)


def database_is_ready() -> bool:
    try:
        db.session.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        db.session.rollback()
        return False


@main_bp.route("/")
def index():
    return render_template("index.html", database_ready=database_is_ready())


@main_bp.route("/hello/<name>")
def hello(name: str):
    return jsonify({"message": f"안녕하세요, {name}!"})


@main_bp.route("/health")
def health():
    ready = database_is_ready()
    return jsonify({
        "status": "ok" if ready else "error",
        "database": "connected" if ready else "disconnected",
    }), 200 if ready else 503

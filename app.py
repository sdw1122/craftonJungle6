import os

from flask import Flask, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import URL, text
from sqlalchemy.exc import SQLAlchemyError

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
    }), 200 if database_ready else 503

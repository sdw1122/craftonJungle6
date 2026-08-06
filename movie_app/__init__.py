import os
from pathlib import Path
from typing import Any

from flask import Flask

from movie_app.config import database_uri
from movie_app.extensions import db
from movie_app.routes.api import api_blueprint
from movie_app.routes.pages import pages_blueprint
from movie_app.services.tmdb import TMDBClient


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=database_uri(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    app.extensions["tmdb_client"] = TMDBClient(os.getenv("TMDB_ACCESS_TOKEN"))
    app.register_blueprint(pages_blueprint)
    app.register_blueprint(api_blueprint)
    return app

import os
from pathlib import Path
from typing import Any

from flask import Flask, redirect, request, url_for
from flask_login import current_user
from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader
from sqlalchemy import URL
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

from .extensions import db, login_manager, oauth
from .errors import register_error_handlers
from .ott_icons import DEFAULT_OTT_ICON, OTT_ICONS


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    app = Flask(__name__)
    # nginx가 https를 처리하고 내부적으로 http로 전달하므로,
    # X-Forwarded-Proto 헤더를 신뢰해 url_for(_external=True)가 https를 쓰도록 함
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
        "postgresql+psycopg",
        username=os.getenv("DB_USER") or os.getenv("POSTGRES_USER", "flask_user"),
        password=os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD", "flask_password"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT") or os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("DB_NAME") or os.getenv("POSTGRES_DB", "flask_app"),
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID")
    app.config["GOOGLE_CLIENT_SECRET"] = os.getenv("GOOGLE_CLIENT_SECRET")
    app.config["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
    app.config["OPENAI_MODEL"] = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    app.config["OPENAI_TIMEOUT_SECONDS"] = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
    app.config["RECOMMENDATION_TTL_HOURS"] = int(os.getenv("RECOMMENDATION_TTL_HOURS", "24"))
    app.config["RECOMMENDATION_LIMIT"] = int(os.getenv("RECOMMENDATION_LIMIT", "10"))
    app.config["RECOMMENDATION_CANDIDATE_LIMIT"] = int(os.getenv("RECOMMENDATION_CANDIDATE_LIMIT", "30"))

    if test_config:
        app.config.update(test_config)

    # 스키마는 db/init/*.sql이 기준(source of truth)입니다.
    # Flask-Migrate/db.create_all()은 사용하지 않습니다 — 여기서는 기존 테이블에 매핑만 합니다.
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    from . import models

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, user_id)

    from .routes.account import account_bp
    from .routes.auth import auth_bp
    from .routes.api import api_blueprint
    from .routes.main import main_bp
    from .routes.onboarding import onboarding_bp
    from .routes.pages import pages_blueprint
    from .routes.reviews import reviews_bp
    from .routes.recommendations import recommendations_bp
    from .routes.search import search_bp
    from .routes.wishlist import wishlist_bp
    from .routes.settings import settings_bp

    from .cli import sync_popular_movies, upgrade_movie_catalog_schema

    project_root = Path(__file__).resolve().parent.parent
    app.jinja_loader = ChoiceLoader([
        app.jinja_loader,
        PrefixLoader({
            "movies": FileSystemLoader(str(project_root / "templates")),
        }),
    ])
    app.cli.add_command(sync_popular_movies)
    app.cli.add_command(upgrade_movie_catalog_schema)

    app.register_blueprint(pages_blueprint)
    app.register_blueprint(api_blueprint)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(wishlist_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(recommendations_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(settings_bp)
    register_error_handlers(app)

    @app.context_processor
    def inject_header_data():
        if not current_user.is_authenticated:
            return {}

        wishlist_counts = {
            "wishlisted": models.UserMovieLibrary.query.filter_by(
                user_id=current_user.id, is_wishlisted=True
            ).count(),
            "watching": models.UserMovieLibrary.query.filter_by(
                user_id=current_user.id, watch_status="WATCHING"
            ).count(),
            "watched": models.UserMovieLibrary.query.filter_by(
                user_id=current_user.id, watch_status="WATCHED"
            ).count(),
        }
        my_ott_subscriptions = (
            models.UserOTTSubscription.query
            .filter_by(user_id=current_user.id, ended_at=None)
            .join(models.OTTProvider)
            .order_by(models.OTTProvider.id)
            .all()
        )
        all_ott_providers = models.OTTProvider.query.filter_by(is_active=True).order_by(models.OTTProvider.id).all()
        my_ott_provider_ids = {sub.provider_id for sub in my_ott_subscriptions}
        return {
            "wishlist_counts": wishlist_counts,
            "my_ott_subscriptions": my_ott_subscriptions,
            "all_ott_providers": all_ott_providers,
            "my_ott_provider_ids": my_ott_provider_ids,
            "ott_icons": OTT_ICONS,
            "default_ott_icon": DEFAULT_OTT_ICON,
        }

    @app.before_request
    def enforce_onboarding():
        if not current_user.is_authenticated:
            return None
        if request.blueprint == "onboarding" or request.endpoint in ("auth.logout", "static"):
            return None
        if current_user.needs_onboarding:
            return redirect(url_for("onboarding.intro"))
        return None

    return app

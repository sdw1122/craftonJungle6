import os

from flask import Flask, redirect, request, url_for
from flask_login import current_user
from sqlalchemy import URL

from .extensions import db, login_manager, oauth


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
        "postgresql+psycopg",
        username=os.getenv("DB_USER", "flask_user"),
        password=os.getenv("DB_PASSWORD", "flask_password"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "flask_app"),
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID")
    app.config["GOOGLE_CLIENT_SECRET"] = os.getenv("GOOGLE_CLIENT_SECRET")

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

    from .routes.auth import auth_bp
    from .routes.main import main_bp
    from .routes.onboarding import onboarding_bp
    from .routes.reviews import reviews_bp
    from .routes.wishlist import wishlist_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(wishlist_bp)
    app.register_blueprint(reviews_bp)

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

from datetime import datetime

from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(db.Model, UserMixin):
    __tablename__ = "users"

    GENDERS = ("MALE", "FEMALE", "OTHER", "UNDISCLOSED")

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    email = db.Column(CITEXT, unique=True)
    nickname = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="ACTIVE")
    gender = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    onboarding_completed_at = db.Column(db.DateTime(timezone=True))
    email_verified_at = db.Column(db.DateTime(timezone=True))
    last_login_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))
    updated_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))
    deleted_at = db.Column(db.DateTime(timezone=True))

    @property
    def needs_onboarding(self) -> bool:
        return self.onboarding_completed_at is None


class AuthAccount(db.Model):
    __tablename__ = "auth_accounts"

    PROVIDERS = ("LOCAL", "GOOGLE")

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = db.Column(db.String(20), nullable=False)
    login_id = db.Column(CITEXT)
    google_sub = db.Column(db.String(255))
    password_hash = db.Column(db.Text)
    password_changed_at = db.Column(db.DateTime(timezone=True))
    last_login_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))
    updated_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))

    user = db.relationship("User", backref="auth_accounts")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = datetime.utcnow()

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)


class Genre(db.Model):
    __tablename__ = "genres"

    id = db.Column(db.SmallInteger, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(50), unique=True, nullable=False)


class UserFavoriteGenre(db.Model):
    __tablename__ = "user_favorite_genres"

    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    genre_id = db.Column(db.SmallInteger, db.ForeignKey("genres.id", ondelete="RESTRICT"), primary_key=True)
    priority = db.Column(db.SmallInteger, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))

    genre = db.relationship("Genre")


class OTTProvider(db.Model):
    __tablename__ = "ott_providers"

    id = db.Column(db.SmallInteger, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    logo_url = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class UserOTTSubscription(db.Model):
    __tablename__ = "user_ott_subscriptions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider_id = db.Column(db.SmallInteger, db.ForeignKey("ott_providers.id", ondelete="RESTRICT"), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))
    ended_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))

    user = db.relationship("User", backref="ott_subscriptions")
    provider = db.relationship("OTTProvider")


class UserMovieLibrary(db.Model):
    __tablename__ = "user_movie_library"

    WATCH_STATUSES = ("WATCHING", "WATCHED")

    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # movies 테이블은 C 담당 — 이 파일에서는 Movie 모델을 정의하지 않고 FK 컬럼만 참조
    movie_id = db.Column(UUID(as_uuid=True), db.ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    is_wishlisted = db.Column(db.Boolean, nullable=False, default=False)
    watch_status = db.Column(db.String(20))
    started_at = db.Column(db.DateTime(timezone=True))
    watched_at = db.Column(db.DateTime(timezone=True))
    updated_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))


class MovieReview(db.Model):
    __tablename__ = "movie_reviews"

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movie_id = db.Column(UUID(as_uuid=True), db.ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    # 1~10, 0.5점 단위 별점을 정수로 표현 (예: 4.5점 -> 9)
    rating_half_steps = db.Column(db.SmallInteger, nullable=False)
    content = db.Column(db.Text)
    contains_spoiler = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))
    updated_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))
    deleted_at = db.Column(db.DateTime(timezone=True))

    @property
    def rating(self) -> float:
        return self.rating_half_steps / 2

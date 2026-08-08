from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(db.Model, UserMixin):
    __tablename__ = "users"

    GENDERS = ("MALE", "FEMALE", "OTHER", "UNDISCLOSED")
    AVATAR_KEYS = ("image1", "image2", "image3", "image4", "image5", "image6", "image7")

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    email = db.Column(CITEXT, unique=True)
    nickname = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="ACTIVE")
    gender = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    avatar_key = db.Column(db.String(20))
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
        self.password_changed_at = datetime.now(timezone.utc)

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


class OTTAvailability(db.Model):
    __tablename__ = "ott_availabilities"

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    movie_id = db.Column(UUID(as_uuid=True), db.ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    provider_id = db.Column(db.SmallInteger, db.ForeignKey("ott_providers.id", ondelete="RESTRICT"), nullable=False)
    region_code = db.Column(db.String(2), nullable=False, default="KR")
    offer_type = db.Column(db.String(20), nullable=False)
    available_from = db.Column(db.Date, nullable=False)
    available_until = db.Column(db.Date)
    content_url = db.Column(db.Text)
    source = db.Column(db.String(50))
    source_updated_at = db.Column(db.DateTime(timezone=True))
    last_checked_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))

    provider = db.relationship("OTTProvider")


class Movie(db.Model):
    __tablename__ = "movies"

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    tmdb_id = db.Column(db.BigInteger, unique=True)
    original_title = db.Column(db.String(300), nullable=False)
    overview = db.Column(db.Text)
    release_date = db.Column(db.Date)
    runtime_minutes = db.Column(db.SmallInteger)
    original_language = db.Column(db.String(10))
    age_rating = db.Column(db.String(20))
    poster_url = db.Column(db.Text)
    backdrop_url = db.Column(db.Text)
    popular_rank = db.Column(db.SmallInteger)
    now_playing_rank = db.Column(db.SmallInteger)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))
    updated_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"))


class MovieTitle(db.Model):
    __tablename__ = "movie_titles"

    id = db.Column(db.BigInteger, primary_key=True)
    movie_id = db.Column(UUID(as_uuid=True), db.ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    locale = db.Column(db.String(10), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    title_type = db.Column(db.String(20), nullable=False)

    movie = db.relationship("Movie", backref="titles")


class MovieGenre(db.Model):
    __tablename__ = "movie_genres"

    movie_id = db.Column(UUID(as_uuid=True), db.ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    genre_id = db.Column(db.SmallInteger, db.ForeignKey("genres.id", ondelete="RESTRICT"), primary_key=True)

    genre = db.relationship("Genre")


class Person(db.Model):
    __tablename__ = "people"

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    tmdb_id = db.Column(db.BigInteger, unique=True)
    primary_name = db.Column(db.String(200), nullable=False)
    birth_date = db.Column(db.Date)


class MovieCredit(db.Model):
    __tablename__ = "movie_credits"

    id = db.Column(db.BigInteger, primary_key=True)
    movie_id = db.Column(UUID(as_uuid=True), db.ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    person_id = db.Column(UUID(as_uuid=True), db.ForeignKey("people.id", ondelete="CASCADE"), nullable=False)
    credit_type = db.Column(db.String(20), nullable=False)
    character_name = db.Column(db.String(200))
    billing_order = db.Column(db.SmallInteger)

    person = db.relationship("Person")


class UserMovieLibrary(db.Model):
    __tablename__ = "user_movie_library"

    WATCH_STATUSES = ("WATCHING", "WATCHED")

    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
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

    user = db.relationship("User")

    @property
    def rating(self) -> float:
        return self.rating_half_steps / 2


class RecommendationRun(db.Model):
    __tablename__ = "recommendation_runs"

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider_id = db.Column(db.SmallInteger, db.ForeignKey("ott_providers.id", ondelete="SET NULL"))
    recommendation_type = db.Column(db.String(30), nullable=False)
    model_name = db.Column(db.String(100), nullable=False)
    feature_version = db.Column(db.String(50), nullable=False)
    context = db.Column(JSONB)
    generated_at = db.Column(db.DateTime(timezone=True), server_default=db.text("CURRENT_TIMESTAMP"), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)

    items = db.relationship(
        "RecommendationItem",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RecommendationItem.rank",
    )


class RecommendationItem(db.Model):
    __tablename__ = "recommendation_items"

    run_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("recommendation_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    movie_id = db.Column(UUID(as_uuid=True), db.ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    rank = db.Column(db.SmallInteger, nullable=False)
    score = db.Column(db.Numeric(8, 6), nullable=False)
    reason_text = db.Column(db.String(500))
    reason_codes = db.Column(JSONB)

    run = db.relationship("RecommendationRun", back_populates="items")
    movie = db.relationship("Movie")

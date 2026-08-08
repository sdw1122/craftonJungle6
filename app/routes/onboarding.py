from datetime import date, datetime, timezone

from flask import Blueprint, current_app, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..extensions import db
from ..models import Genre, OTTProvider, User, UserFavoriteGenre, UserOTTSubscription
from ..ott_icons import DEFAULT_OTT_ICON, OTT_ICONS
from .validation import parse_positive_int_set

onboarding_bp = Blueprint("onboarding", __name__, url_prefix="/onboarding")

GENDER_LABELS = {
    "MALE": "남성",
    "FEMALE": "여성",
    "OTHER": "기타",
    "UNDISCLOSED": "선택 안 함",
}


@onboarding_bp.route("/")
@login_required
def intro():
    if not current_user.needs_onboarding:
        return redirect(url_for("pages.index"))
    return render_template("onboarding/intro.html")


@onboarding_bp.route("/avatar", methods=["GET", "POST"])
@login_required
def avatar():
    if request.method == "POST":
        avatar_key = request.form.get("avatar_key")
        if avatar_key not in User.AVATAR_KEYS:
            return render_template("onboarding/avatar.html", error="프로필 이미지를 선택해주세요."), 400
        current_user.avatar_key = avatar_key
        db.session.commit()
        return redirect(url_for("onboarding.gender"))
    return render_template("onboarding/avatar.html")


@onboarding_bp.route("/gender", methods=["GET", "POST"])
@login_required
def gender():
    if request.method == "POST":
        gender_value = request.form.get("gender")
        if gender_value not in User.GENDERS:
            return render_template("onboarding/gender.html", labels=GENDER_LABELS, error="성별을 선택해주세요."), 400
        current_user.gender = gender_value
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to save onboarding gender")
            return render_template(
                "onboarding/gender.html",
                labels=GENDER_LABELS,
                error="성별을 저장하지 못했습니다. 다시 시도해 주세요.",
            ), 503
        return redirect(url_for("onboarding.birthdate"))
    return render_template("onboarding/gender.html", labels=GENDER_LABELS)


@onboarding_bp.route("/birthdate", methods=["GET", "POST"])
@login_required
def birthdate():
    if request.method == "POST":
        try:
            birth_date = date(
                int(request.form["year"]),
                int(request.form["month"]),
                int(request.form["day"]),
            )
        except (KeyError, ValueError):
            return render_template("onboarding/birthdate.html", error="생년월일을 정확히 입력해주세요."), 400
        if birth_date > date.today():
            return render_template("onboarding/birthdate.html", error="미래 날짜는 입력할 수 없습니다."), 400
        if birth_date < date(1900, 1, 1):
            return render_template("onboarding/birthdate.html", error="1900년 이후 날짜를 입력해 주세요."), 400

        current_user.birth_date = birth_date
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to save onboarding birth date")
            return render_template(
                "onboarding/birthdate.html",
                error="생년월일을 저장하지 못했습니다. 다시 시도해 주세요.",
            ), 503
        return redirect(url_for("onboarding.genres"))
    return render_template("onboarding/birthdate.html")


@onboarding_bp.route("/genres", methods=["GET", "POST"])
@login_required
def genres():
    genre_list = Genre.query.order_by(Genre.name).all()

    if request.method == "POST":
        picks = []
        for p in (1, 2, 3):
            raw = request.form.get(f"priority_{p}")
            if raw:
                try:
                    genre_id = int(raw)
                except (TypeError, ValueError):
                    return render_template(
                        "onboarding/genres.html",
                        genre_list=genre_list,
                        error="올바른 장르를 선택해 주세요.",
                    ), 400
                if genre_id <= 0:
                    return render_template(
                        "onboarding/genres.html",
                        genre_list=genre_list,
                        error="올바른 장르를 선택해 주세요.",
                    ), 400
                picks.append(genre_id)

        valid_genre_ids = {genre.id for genre in genre_list}
        if (
            not picks
            or len(picks) != len(set(picks))
            or not set(picks).issubset(valid_genre_ids)
        ):
            return render_template(
                "onboarding/genres.html",
                genre_list=genre_list,
                error="목록에 있는 서로 다른 장르를 1개 이상 선택해 주세요.",
            ), 400

        try:
            UserFavoriteGenre.query.filter_by(user_id=current_user.id).delete()
            for priority, genre_id in enumerate(picks, start=1):
                db.session.add(UserFavoriteGenre(user_id=current_user.id, genre_id=genre_id, priority=priority))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            current_app.logger.warning("Favorite genre update conflict", exc_info=True)
            return render_template(
                "onboarding/genres.html",
                genre_list=genre_list,
                error="장르 설정이 충돌했습니다. 다시 시도해 주세요.",
            ), 409
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to save favorite genres")
            return render_template(
                "onboarding/genres.html",
                genre_list=genre_list,
                error="장르를 저장하지 못했습니다. 다시 시도해 주세요.",
            ), 503
        return redirect(url_for("onboarding.ott"))

    return render_template("onboarding/genres.html", genre_list=genre_list)


@onboarding_bp.route("/ott", methods=["GET", "POST"])
@login_required
def ott():
    ott_choices = OTTProvider.query.filter_by(is_active=True).order_by(OTTProvider.id).all()

    if request.method == "POST":
        try:
            selected_ids = parse_positive_int_set(request.form.getlist("provider_id"))
        except ValueError:
            return render_template(
                "onboarding/ott.html",
                otts=ott_choices,
                icons=OTT_ICONS,
                default_icon=DEFAULT_OTT_ICON,
                error="올바른 OTT 서비스를 선택해 주세요.",
            ), 400

        valid_provider_ids = {provider.id for provider in ott_choices}
        if not selected_ids.issubset(valid_provider_ids):
            return render_template(
                "onboarding/ott.html",
                otts=ott_choices,
                icons=OTT_ICONS,
                default_icon=DEFAULT_OTT_ICON,
                error="존재하지 않거나 이용할 수 없는 OTT 서비스입니다.",
            ), 400

        try:
            active_subs = UserOTTSubscription.query.filter_by(
                user_id=current_user.id, ended_at=None
            ).all()
            active_by_provider = {sub.provider_id: sub for sub in active_subs}

            for provider_id, sub in active_by_provider.items():
                if provider_id not in selected_ids:
                    sub.ended_at = datetime.now(timezone.utc)

            for provider_id in selected_ids:
                if provider_id not in active_by_provider:
                    db.session.add(UserOTTSubscription(user_id=current_user.id, provider_id=provider_id))

            current_user.onboarding_completed_at = datetime.now(timezone.utc)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            current_app.logger.warning("Onboarding OTT update conflict", exc_info=True)
            return render_template(
                "onboarding/ott.html",
                otts=ott_choices,
                icons=OTT_ICONS,
                default_icon=DEFAULT_OTT_ICON,
                error="OTT 설정이 충돌했습니다. 다시 시도해 주세요.",
            ), 409
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to save onboarding OTT subscriptions")
            return render_template(
                "onboarding/ott.html",
                otts=ott_choices,
                icons=OTT_ICONS,
                default_icon=DEFAULT_OTT_ICON,
                error="OTT 설정을 저장하지 못했습니다. 다시 시도해 주세요.",
            ), 503
        return redirect(url_for("onboarding.complete"))

    return render_template(
        "onboarding/ott.html",
        otts=ott_choices,
        icons=OTT_ICONS,
        default_icon=DEFAULT_OTT_ICON,
    )


@onboarding_bp.route("/complete")
@login_required
def complete():
    if current_user.needs_onboarding:
        return redirect(url_for("onboarding.intro"))
    return render_template("onboarding/complete.html")

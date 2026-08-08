from datetime import date, datetime

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Genre, OTTProvider, User, UserFavoriteGenre, UserOTTSubscription
from ..ott_icons import DEFAULT_OTT_ICON, OTT_ICONS

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
        db.session.commit()
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

        current_user.birth_date = birth_date
        db.session.commit()
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
                picks.append(int(raw))

        if not picks or len(picks) != len(set(picks)):
            return render_template(
                "onboarding/genres.html",
                genre_list=genre_list,
                error="서로 다른 장르로 1개 이상 선택해주세요.",
            ), 400

        UserFavoriteGenre.query.filter_by(user_id=current_user.id).delete()
        for priority, genre_id in enumerate(picks, start=1):
            db.session.add(UserFavoriteGenre(user_id=current_user.id, genre_id=genre_id, priority=priority))
        db.session.commit()
        return redirect(url_for("onboarding.ott"))

    return render_template("onboarding/genres.html", genre_list=genre_list)


@onboarding_bp.route("/ott", methods=["GET", "POST"])
@login_required
def ott():
    ott_choices = OTTProvider.query.filter_by(is_active=True).order_by(OTTProvider.id).all()

    if request.method == "POST":
        selected_ids = {int(v) for v in request.form.getlist("provider_id") if v.isdigit()}

        active_subs = UserOTTSubscription.query.filter_by(
            user_id=current_user.id, ended_at=None
        ).all()
        active_by_provider = {sub.provider_id: sub for sub in active_subs}

        for provider_id, sub in active_by_provider.items():
            if provider_id not in selected_ids:
                sub.ended_at = datetime.utcnow()

        for provider_id in selected_ids:
            if provider_id not in active_by_provider:
                db.session.add(UserOTTSubscription(user_id=current_user.id, provider_id=provider_id))

        current_user.onboarding_completed_at = datetime.utcnow()
        db.session.commit()
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

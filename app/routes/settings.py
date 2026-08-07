from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import AuthAccount


settings_bp = Blueprint(
    "settings",
    __name__,
    url_prefix="/settings",
)


@settings_bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    local_account = AuthAccount.query.filter_by(
        user_id=current_user.id,
        provider="LOCAL",
    ).first()

    if local_account is None:
        flash("소셜 로그인 계정은 변경할 비밀번호가 없습니다.")
        return redirect(url_for("pages.settings"))

    if request.method == "GET":
        return render_template("settings/change_password.html")

    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not current_password:
        flash("현재 비밀번호를 입력해 주세요.")
        return redirect(url_for("settings.change_password"))

    if not new_password:
        flash("새 비밀번호를 입력해 주세요.")
        return redirect(url_for("settings.change_password"))

    if not confirm_password:
        flash("새 비밀번호 확인을 입력해 주세요.")
        return redirect(url_for("settings.change_password"))

    if not local_account.check_password(current_password):
        flash("현재 비밀번호가 올바르지 않습니다.")
        return redirect(url_for("settings.change_password"))

    if len(new_password) < 8:
        flash("새 비밀번호는 8자 이상이어야 합니다.")
        return redirect(url_for("settings.change_password"))

    if len(new_password) > 128:
        flash("새 비밀번호는 128자 이하여야 합니다.")
        return redirect(url_for("settings.change_password"))

    if new_password != confirm_password:
        flash("새 비밀번호와 비밀번호 확인이 일치하지 않습니다.")
        return redirect(url_for("settings.change_password"))

    if local_account.check_password(new_password):
        flash("현재 비밀번호와 다른 비밀번호를 입력해 주세요.")
        return redirect(url_for("settings.change_password"))

    local_account.set_password(new_password)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to change local password")
        flash("비밀번호를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return redirect(url_for("settings.change_password"))

    flash("비밀번호가 성공적으로 변경되었습니다.")
    return redirect(url_for("pages.settings"))

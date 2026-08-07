from datetime import datetime, timezone

from flask import Blueprint, current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..extensions import db
from ..models import OTTProvider, UserOTTSubscription
from .validation import parse_positive_int_set

account_bp = Blueprint("account", __name__, url_prefix="/me")


@account_bp.route("/ott-subscriptions", methods=["POST"])
@login_required
def update_ott_subscriptions():
    try:
        selected_ids = parse_positive_int_set(request.form.getlist("provider_id"))
    except ValueError:
        flash("올바른 OTT 서비스를 선택해 주세요.")
        return redirect(request.referrer or url_for("pages.index"))

    valid_provider_ids = {
        provider_id
        for (provider_id,) in (
            db.session.query(OTTProvider.id)
            .filter_by(is_active=True)
            .all()
        )
    }
    if not selected_ids.issubset(valid_provider_ids):
        flash("존재하지 않거나 이용할 수 없는 OTT 서비스입니다.")
        return redirect(request.referrer or url_for("pages.index"))

    try:
        active_subs = UserOTTSubscription.query.filter_by(user_id=current_user.id, ended_at=None).all()
        active_by_provider = {sub.provider_id: sub for sub in active_subs}

        for provider_id, sub in active_by_provider.items():
            if provider_id not in selected_ids:
                sub.ended_at = datetime.now(timezone.utc)

        for provider_id in selected_ids:
            if provider_id not in active_by_provider:
                db.session.add(UserOTTSubscription(user_id=current_user.id, provider_id=provider_id))

        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.warning("OTT subscription update conflict", exc_info=True)
        flash("OTT 설정이 동시에 변경되었습니다. 다시 시도해 주세요.")
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to update OTT subscriptions")
        flash("OTT 설정을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    return redirect(request.referrer or url_for("pages.index"))

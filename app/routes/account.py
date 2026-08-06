from datetime import datetime

from flask import Blueprint, redirect, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import UserOTTSubscription

account_bp = Blueprint("account", __name__, url_prefix="/me")


@account_bp.route("/ott-subscriptions", methods=["POST"])
@login_required
def update_ott_subscriptions():
    selected_ids = {int(v) for v in request.form.getlist("provider_id") if v.isdigit()}

    active_subs = UserOTTSubscription.query.filter_by(user_id=current_user.id, ended_at=None).all()
    active_by_provider = {sub.provider_id: sub for sub in active_subs}

    for provider_id, sub in active_by_provider.items():
        if provider_id not in selected_ids:
            sub.ended_at = datetime.utcnow()

    for provider_id in selected_ids:
        if provider_id not in active_by_provider:
            db.session.add(UserOTTSubscription(user_id=current_user.id, provider_id=provider_id))

    db.session.commit()
    return redirect(request.referrer or url_for("main.index"))

from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import UserMovieLibrary

wishlist_bp = Blueprint("wishlist", __name__, url_prefix="/wishlist")


def _get_or_create_entry(movie_id):
    entry = UserMovieLibrary.query.filter_by(user_id=current_user.id, movie_id=movie_id).first()
    if entry is None:
        entry = UserMovieLibrary(user_id=current_user.id, movie_id=movie_id, is_wishlisted=False)
        db.session.add(entry)
    return entry


def _serialize(entry: UserMovieLibrary) -> dict:
    return {
        "movie_id": str(entry.movie_id),
        "is_wishlisted": entry.is_wishlisted,
        "watch_status": entry.watch_status,
    }


@wishlist_bp.route("/<uuid:movie_id>", methods=["POST"])
@login_required
def upsert(movie_id):
    payload = request.get_json(silent=True) or request.form

    entry = _get_or_create_entry(movie_id)

    if "is_wishlisted" in payload:
        raw = payload.get("is_wishlisted")
        entry.is_wishlisted = str(raw).strip().lower() in ("1", "true", "on", "yes")

    if "watch_status" in payload:
        watch_status = payload.get("watch_status") or None
        if watch_status is not None and watch_status not in UserMovieLibrary.WATCH_STATUSES:
            abort(400, description=f"watch_status must be one of {UserMovieLibrary.WATCH_STATUSES}")
        entry.watch_status = watch_status
        if watch_status == "WATCHING" and entry.started_at is None:
            entry.started_at = datetime.utcnow()
        if watch_status == "WATCHED":
            entry.watched_at = datetime.utcnow()

    entry.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize(entry))


@wishlist_bp.route("/<uuid:movie_id>", methods=["DELETE"])
@login_required
def remove(movie_id):
    entry = UserMovieLibrary.query.filter_by(user_id=current_user.id, movie_id=movie_id).first()
    if entry is None:
        abort(404)
    db.session.delete(entry)
    db.session.commit()
    return "", 204

from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import MovieReview

reviews_bp = Blueprint("reviews", __name__, url_prefix="/reviews")


def _serialize(review: MovieReview) -> dict:
    return {
        "movie_id": str(review.movie_id),
        "rating": review.rating,
        "content": review.content,
        "contains_spoiler": review.contains_spoiler,
    }


@reviews_bp.route("/<uuid:movie_id>", methods=["POST"])
@login_required
def upsert(movie_id):
    payload = request.get_json(silent=True) or request.form

    try:
        # 0.5 단위 별점(예: 4.5)을 입력받아 내부적으로 half-step 정수(1~10)로 저장
        rating = float(payload["rating"])
    except (KeyError, TypeError, ValueError):
        abort(400, description="rating(0.5~5.0, 0.5 단위)이 필요합니다.")
    if not 0.5 <= rating <= 5 or (rating * 2) % 1 != 0:
        abort(400, description="rating은 0.5~5.0 사이의 0.5 단위 값이어야 합니다.")

    review = MovieReview.query.filter_by(user_id=current_user.id, movie_id=movie_id).first()
    if review is None:
        review = MovieReview(user_id=current_user.id, movie_id=movie_id)
        db.session.add(review)

    review.rating_half_steps = int(rating * 2)
    review.content = payload.get("content", "")
    review.contains_spoiler = str(payload.get("contains_spoiler", False)).strip().lower() in (
        "1", "true", "on", "yes",
    )
    review.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize(review))


@reviews_bp.route("/<uuid:movie_id>", methods=["DELETE"])
@login_required
def delete(movie_id):
    review = MovieReview.query.filter_by(user_id=current_user.id, movie_id=movie_id).first()
    if review is None:
        abort(404)
    db.session.delete(review)
    db.session.commit()
    return "", 204

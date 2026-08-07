from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..extensions import db
from ..models import Movie, MovieReview
from ..movie_sync import get_or_create_movie

reviews_bp = Blueprint("reviews", __name__, url_prefix="/reviews")


def _serialize(review: MovieReview) -> dict:
    return {
        "movie_id": str(review.movie_id),
        "rating": review.rating,
        "content": review.content,
        "contains_spoiler": review.contains_spoiler,
    }


def _mutation_error(message: str, status_code: int):
    if request.is_json:
        return jsonify({"message": message}), status_code
    flash(message)
    return redirect(request.referrer or url_for("pages.index"))


@reviews_bp.route("/<int:tmdb_id>", methods=["POST"])
@login_required
def upsert(tmdb_id: int):
    payload = request.get_json(silent=True) or request.form

    try:
        # 0.5 단위 별점(예: 4.5)을 입력받아 내부적으로 half-step 정수(1~10)로 저장
        rating = float(payload["rating"])
    except (KeyError, TypeError, ValueError):
        abort(400, description="rating(0.5~5.0, 0.5 단위)이 필요합니다.")
    if not 0.5 <= rating <= 5 or (rating * 2) % 1 != 0:
        abort(400, description="rating은 0.5~5.0 사이의 0.5 단위 값이어야 합니다.")

    try:
        movie = get_or_create_movie(
            tmdb_id=tmdb_id,
            title=payload.get("title"),
            overview=payload.get("overview"),
            release_date=payload.get("release_date"),
            poster_url=payload.get("poster_url"),
        )

        review = MovieReview.query.filter_by(user_id=current_user.id, movie_id=movie.id).first()
        if review is None:
            review = MovieReview(user_id=current_user.id, movie_id=movie.id)
            db.session.add(review)

        review.rating_half_steps = int(rating * 2)
        review.content = payload.get("content", "")
        review.contains_spoiler = str(payload.get("contains_spoiler", False)).strip().lower() in (
            "1", "true", "on", "yes",
        )
        review.updated_at = datetime.now(timezone.utc)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.warning("Review update conflict", exc_info=True)
        return _mutation_error("리뷰가 동시에 변경되었습니다. 다시 시도해 주세요.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to save review")
        return _mutation_error("리뷰를 저장하지 못했습니다.", 503)

    if request.is_json:
        return jsonify(_serialize(review))

    return redirect(request.referrer or url_for("pages.index"))


@reviews_bp.route("/<int:tmdb_id>", methods=["DELETE"])
@login_required
def delete(tmdb_id: int):
    try:
        movie = Movie.query.filter_by(tmdb_id=tmdb_id).first()
        if movie is None:
            abort(404)
        review = MovieReview.query.filter_by(user_id=current_user.id, movie_id=movie.id).first()
        if review is None:
            abort(404)
        db.session.delete(review)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to delete review")
        return _mutation_error("리뷰를 삭제하지 못했습니다.", 503)
    return "", 204

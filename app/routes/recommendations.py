from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from ..services.recommendations import RecommendationUnavailable, get_recommendation_service


recommendations_bp = Blueprint("recommendations", __name__, url_prefix="/api/recommendations")


def _validate_limit(raw_value) -> int:
    try:
        limit = int(raw_value)
    except (TypeError, ValueError):
        raise ValueError("limit은 1부터 20 사이의 정수여야 합니다.") from None
    if not 1 <= limit <= 20:
        raise ValueError("limit은 1부터 20 사이의 정수여야 합니다.")
    return limit


@recommendations_bp.get("")
@login_required
def get_recommendations():
    try:
        limit = _validate_limit(request.args.get("limit", current_app.config["RECOMMENDATION_LIMIT"]))
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    payload = get_recommendation_service().get_cached(
        getattr(current_user, "id", None) or current_user.get_id(),
        limit,
    )
    return jsonify(payload)


@recommendations_bp.post("")
@login_required
def generate_recommendations():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"message": "JSON 객체 형식의 요청이 필요합니다."}), 400
    try:
        limit = _validate_limit(body.get("limit", current_app.config["RECOMMENDATION_LIMIT"]))
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    force = body.get("force", False)
    if not isinstance(force, bool):
        return jsonify({"message": "force는 boolean 값이어야 합니다."}), 400

    try:
        payload = get_recommendation_service().generate(
            getattr(current_user, "id", None) or current_user.get_id(),
            limit,
            force=force,
        )
    except RecommendationUnavailable as exc:
        return jsonify({"message": str(exc)}), 503
    except SQLAlchemyError:
        # RecommendationService rolls back persistence failures. This rollback also
        # covers failures raised while loading the profile or catalog.
        from ..extensions import db

        db.session.rollback()
        current_app.logger.exception("Failed to generate recommendations")
        return jsonify({"message": "추천 결과를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."}), 503
    return jsonify(payload)

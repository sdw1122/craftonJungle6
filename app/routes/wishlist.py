from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..extensions import db
from ..models import Movie, OTTAvailability, OTTProvider, UserMovieLibrary
from ..movie_sync import get_or_create_movie
from ..ott_icons import BOX_OFFICE_ICON, DEFAULT_OTT_ICON, OTT_ICONS
from ..services.movie_catalog_query import serialize_movie_summary, streaming_movie_ids

wishlist_bp = Blueprint("wishlist", __name__, url_prefix="/wishlist")

LIBRARY_TABS = {
    "wishlisted": "찜했어요",
    "watching": "보는중",
    "watched": "봤어요",
}


@wishlist_bp.route("/", methods=["GET"])
@login_required
def library():
    status = request.args.get("status", "wishlisted")
    if status not in LIBRARY_TABS:
        abort(404)
    ott_filter = request.args.get("ott", "all")

    query = UserMovieLibrary.query.filter_by(user_id=current_user.id)
    if status == "wishlisted":
        query = query.filter_by(is_wishlisted=True)
    else:
        query = query.filter_by(watch_status=status.upper())

    entries = query.order_by(UserMovieLibrary.updated_at.desc()).all()
    movie_ids = [e.movie_id for e in entries]
    movies_by_id = {
        m.id: m for m in Movie.query.filter(Movie.id.in_(movie_ids)).all()
    } if movie_ids else {}

    if ott_filter != "all":
        if ott_filter == "box-office":
            available_ids = {
                movie.id for movie in Movie.query.filter(
                    Movie.id.in_(movie_ids),
                    Movie.now_playing_rank.isnot(None),
                ).all()
            }
        else:
            try:
                ott_provider_id = int(ott_filter)
            except ValueError:
                abort(400)
            available_ids = {
                row.movie_id for row in OTTAvailability.query.filter(
                    OTTAvailability.movie_id.in_(movie_ids),
                    OTTAvailability.provider_id == ott_provider_id,
                ).all()
            }
        movies_by_id = {mid: m for mid, m in movies_by_id.items() if mid in available_ids}

    if status == "wishlisted":
        remove_payload = {"is_wishlisted": "false"}
    else:
        remove_payload = {"watch_status": ""}

    streaming_ids = streaming_movie_ids(list(movies_by_id))
    items = [
        {
            "movie": movies_by_id[e.movie_id],
            "summary": serialize_movie_summary(
                movies_by_id[e.movie_id],
                is_streaming=e.movie_id in streaming_ids,
            ),
        }
        for e in entries
        if e.movie_id in movies_by_id
    ]

    all_ott_providers = OTTProvider.query.filter_by(is_active=True).order_by(OTTProvider.id).all()

    return render_template(
        "wishlist/library.html",
        page_title=LIBRARY_TABS[status],
        status=status,
        tabs=LIBRARY_TABS,
        items=items,
        ott_filter=ott_filter,
        all_ott_providers=all_ott_providers,
        ott_icons=OTT_ICONS,
        default_ott_icon=DEFAULT_OTT_ICON,
        box_office_icon=BOX_OFFICE_ICON,
        remove_payload=remove_payload,
    )


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


def _mutation_error(message: str, status_code: int):
    if request.is_json:
        return jsonify({"message": message}), status_code
    flash(message)
    return redirect(request.referrer or url_for("pages.index"))


@wishlist_bp.route("/<int:tmdb_id>", methods=["POST"])
@login_required
def upsert(tmdb_id: int):
    payload = request.get_json(silent=True) or request.form

    watch_status = None
    if "watch_status" in payload:
        watch_status = payload.get("watch_status") or None
        if watch_status is not None and watch_status not in UserMovieLibrary.WATCH_STATUSES:
            abort(400, description=f"watch_status must be one of {UserMovieLibrary.WATCH_STATUSES}")

    try:
        movie = get_or_create_movie(
            tmdb_id=tmdb_id,
            title=payload.get("title"),
            overview=payload.get("overview"),
            release_date=payload.get("release_date"),
            poster_url=payload.get("poster_url"),
        )
        entry = _get_or_create_entry(movie.id)

        if "is_wishlisted" in payload:
            raw = payload.get("is_wishlisted")
            entry.is_wishlisted = str(raw).strip().lower() in ("1", "true", "on", "yes")

        if "watch_status" in payload:
            entry.watch_status = watch_status
            if watch_status == "WATCHING" and entry.started_at is None:
                entry.started_at = datetime.now(timezone.utc)
            if watch_status == "WATCHED":
                entry.watched_at = datetime.now(timezone.utc)

        entry.updated_at = datetime.now(timezone.utc)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.warning("Wishlist update conflict", exc_info=True)
        return _mutation_error("찜 또는 시청 상태가 동시에 변경되었습니다. 다시 시도해 주세요.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to update wishlist")
        return _mutation_error("찜 또는 시청 상태를 저장하지 못했습니다.", 503)

    if request.is_json:
        return jsonify(_serialize(entry))

    return redirect(request.referrer or url_for("pages.index"))


@wishlist_bp.route("/<int:tmdb_id>", methods=["DELETE"])
@login_required
def remove(tmdb_id: int):
    try:
        movie = Movie.query.filter_by(tmdb_id=tmdb_id).first()
        if movie is None:
            abort(404)
        entry = UserMovieLibrary.query.filter_by(user_id=current_user.id, movie_id=movie.id).first()
        if entry is None:
            abort(404)
        db.session.delete(entry)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to delete wishlist entry")
        return _mutation_error("찜 또는 시청 기록을 삭제하지 못했습니다.", 503)
    return "", 204

from __future__ import annotations

from html import escape

from flask import Response, current_app, jsonify, render_template, request
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import BadRequest, InternalServerError, NotFound

from .extensions import db


def wants_json_response() -> bool:
    return (
        request.path.startswith("/api/")
        or request.is_json
        or request.accept_mimetypes.best == "application/json"
    )


def _log_http_error(status_code: int, error: Exception) -> None:
    current_app.logger.warning(
        "HTTP %s on %s %s: %s",
        status_code,
        request.method,
        request.path,
        error,
    )


def _render_http_error(status_code: int, title: str, message: str):
    if wants_json_response():
        return jsonify({"message": message}), status_code
    return render_template(
        "movies/error.html",
        status_code=status_code,
        title=title,
        message=message,
    ), status_code


def _safe_rollback() -> None:
    try:
        db.session.rollback()
    except SQLAlchemyError:
        current_app.logger.exception("Failed to roll back database session")


def register_error_handlers(app) -> None:
    @app.errorhandler(BadRequest)
    def handle_bad_request(error: BadRequest):
        _log_http_error(400, error)
        message = error.description or "요청 내용을 확인해 주세요."
        return _render_http_error(400, "잘못된 요청입니다.", message)

    @app.errorhandler(NotFound)
    def handle_not_found(error: NotFound):
        _log_http_error(404, error)
        return _render_http_error(
            404,
            "페이지를 찾을 수 없습니다.",
            "요청한 페이지나 데이터를 찾을 수 없습니다.",
        )

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error: SQLAlchemyError):
        _safe_rollback()
        current_app.logger.error(
            "Unhandled database error on %s %s",
            request.method,
            request.path,
            exc_info=(type(error), error, error.__traceback__),
        )
        message = "현재 데이터 저장소를 이용할 수 없습니다. 잠시 후 다시 시도해 주세요."
        if wants_json_response():
            return jsonify({"message": message}), 503

        # Rendering a template would run context processors that query the database
        # and could raise the same error recursively.
        body = (
            "<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\">"
            "<title>서비스 일시 오류</title><body>"
            "<h1>서비스를 잠시 이용할 수 없습니다.</h1>"
            f"<p>{escape(message)}</p>"
            "</body></html>"
        )
        return Response(body, status=503, content_type="text/html; charset=utf-8")

    @app.errorhandler(InternalServerError)
    def handle_internal_server_error(error: InternalServerError):
        _safe_rollback()
        original = error.original_exception or error
        current_app.logger.error(
            "Unhandled application error on %s %s",
            request.method,
            request.path,
            exc_info=(type(original), original, original.__traceback__),
        )
        return _render_http_error(
            500,
            "서비스 오류가 발생했습니다.",
            "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )

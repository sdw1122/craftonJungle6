import unittest
from unittest.mock import patch

from flask import abort
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db


class ErrorHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "PROPAGATE_EXCEPTIONS": False,
        })

        @self.app.get("/_test/bad-request")
        def bad_request():
            abort(400, description="입력값 오류")

        @self.app.get("/_test/application-error")
        def application_error():
            raise RuntimeError("unexpected failure")

        @self.app.get("/api/_test/database-error")
        def database_error():
            raise SQLAlchemyError("database unavailable")

        self.client = self.app.test_client()

    def test_bad_request_uses_json_for_json_clients(self):
        response = self.client.get(
            "/_test/bad-request",
            headers={"Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"message": "입력값 오류"})

    def test_missing_api_route_uses_json(self):
        response = self.client.get("/api/does-not-exist")

        self.assertEqual(response.status_code, 404)
        self.assertIn("찾을 수 없습니다", response.get_json()["message"])

    def test_unhandled_application_error_uses_safe_500_page(self):
        with patch.object(self.app.logger, "error"):
            response = self.client.get("/_test/application-error")

        self.assertEqual(response.status_code, 500)
        self.assertIn("서비스 오류가 발생했습니다", response.get_data(as_text=True))
        self.assertNotIn("unexpected failure", response.get_data(as_text=True))

    def test_database_error_rolls_back_and_returns_json_503(self):
        with (
            patch.object(db.session, "rollback") as rollback,
            patch.object(self.app.logger, "error"),
        ):
            response = self.client.get("/api/_test/database-error")

        self.assertEqual(response.status_code, 503)
        self.assertIn("데이터 저장소", response.get_json()["message"])
        rollback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

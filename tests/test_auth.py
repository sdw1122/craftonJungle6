import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_app
from app.extensions import db, oauth
from app.models import AuthAccount, User
from app.routes.auth import google_callback, signup


class SignupTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})

    def test_signup_rejects_an_existing_user_email(self):
        with self.app.test_request_context(
            "/signup",
            method="POST",
            data={
                "email": "existing@example.com",
                "nickname": "new-nickname",
                "password": "password123",
            },
        ):
            with (
                patch.object(User, "query") as user_query,
                patch.object(db.session, "add") as add,
            ):
                user_query.filter_by.return_value.first.return_value = object()

                response = signup()

                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.location.endswith("/signup"))
                self.assertIn("이미 가입된 이메일", self._flashed_message())
                add.assert_not_called()

    def test_signup_rolls_back_a_unique_constraint_race(self):
        with self.app.test_request_context(
            "/signup",
            method="POST",
            data={
                "email": "new@example.com",
                "nickname": "new-nickname",
                "password": "password123",
            },
        ):
            with (
                patch.object(User, "query") as user_query,
                patch.object(db.session, "add"),
                patch.object(
                    db.session,
                    "flush",
                    side_effect=IntegrityError("INSERT INTO users", {}, Exception("duplicate")),
                ),
                patch.object(db.session, "rollback") as rollback,
            ):
                user_query.filter_by.return_value.first.return_value = None

                response = signup()

                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.location.endswith("/signup"))
                self.assertIn("이미 사용 중인 이메일", self._flashed_message())
                rollback.assert_called_once_with()

    def test_signup_rolls_back_an_unavailable_database(self):
        with self.app.test_request_context(
            "/signup",
            method="POST",
            data={
                "email": "new@example.com",
                "nickname": "new-nickname",
                "password": "password123",
            },
        ):
            with (
                patch.object(User, "query") as user_query,
                patch.object(db.session, "add"),
                patch.object(
                    db.session,
                    "flush",
                    side_effect=SQLAlchemyError("database unavailable"),
                ),
                patch.object(db.session, "rollback") as rollback,
                patch.object(self.app.logger, "exception"),
            ):
                user_query.filter_by.return_value.first.return_value = None

                response = signup()

                self.assertEqual(response.status_code, 302)
                self.assertIn("저장하지 못했습니다", self._flashed_message())
                rollback.assert_called_once_with()

    def test_google_callback_failure_returns_to_login(self):
        with (
            patch.object(
                oauth.google,
                "authorize_access_token",
                side_effect=RuntimeError("oauth unavailable"),
            ),
            patch.object(self.app.logger, "exception"),
        ):
            response = self.app.test_client().get("/auth/google/callback")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login"))

    def test_google_callback_rejects_an_unverified_email(self):
        token = {
            "userinfo": {
                "email": "unverified@example.com",
                "sub": "google-sub",
                "email_verified": False,
            }
        }
        with patch.object(oauth.google, "authorize_access_token", return_value=token):
            response = self.app.test_client().get("/auth/google/callback")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login"))

    def test_google_account_link_conflict_rolls_back(self):
        token = {
            "userinfo": {
                "email": "local@example.com",
                "sub": "google-sub",
                "email_verified": True,
            }
        }
        existing_user = SimpleNamespace(id="user-id")
        error = IntegrityError("INSERT", {}, Exception("duplicate"))

        with self.app.test_request_context("/auth/google/callback"):
            with (
                patch.object(oauth.google, "authorize_access_token", return_value=token),
                patch.object(AuthAccount, "query") as account_query,
                patch.object(User, "query") as user_query,
                patch.object(db.session, "add"),
                patch.object(db.session, "commit", side_effect=error),
                patch.object(db.session, "rollback") as rollback,
                patch.object(self.app.logger, "warning"),
            ):
                account_query.filter_by.return_value.first.return_value = None
                user_query.filter_by.return_value.first.return_value = existing_user

                response = google_callback()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login"))
        rollback.assert_called_once_with()

    @staticmethod
    def _flashed_message():
        from flask import session

        return session["_flashes"][-1][1]


if __name__ == "__main__":
    unittest.main()

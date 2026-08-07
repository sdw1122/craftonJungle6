import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_app
from app.extensions import db
from app.models import Genre, UserFavoriteGenre, UserOTTSubscription
from app.routes.account import update_ott_subscriptions
from app.routes.onboarding import genres
from app.routes.wishlist import upsert as upsert_wishlist


class MutationErrorTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.user = SimpleNamespace(id="00000000-0000-0000-0000-000000000001")

    def test_genres_rejects_a_non_numeric_id(self):
        with self.app.test_request_context(
            "/onboarding/genres",
            method="POST",
            data={"priority_1": "not-a-number"},
        ):
            with (
                patch("app.routes.onboarding.current_user", self.user),
                patch.object(Genre, "query") as genre_query,
                patch.object(db.session, "commit") as commit,
            ):
                genre_query.order_by.return_value.all.return_value = [
                    SimpleNamespace(id=1, name="드라마")
                ]

                response, status = genres.__wrapped__()

        self.assertEqual(status, 400)
        self.assertIn("올바른 장르", response)
        commit.assert_not_called()

    def test_genres_rejects_an_unknown_foreign_key(self):
        with self.app.test_request_context(
            "/onboarding/genres",
            method="POST",
            data={"priority_1": "999"},
        ):
            with (
                patch("app.routes.onboarding.current_user", self.user),
                patch.object(Genre, "query") as genre_query,
                patch.object(db.session, "commit") as commit,
            ):
                genre_query.order_by.return_value.all.return_value = [
                    SimpleNamespace(id=1, name="드라마")
                ]

                response, status = genres.__wrapped__()

        self.assertEqual(status, 400)
        self.assertIn("목록에 있는", response)
        commit.assert_not_called()

    def test_genre_constraint_conflict_rolls_back(self):
        error = IntegrityError("INSERT", {}, Exception("duplicate"))
        with self.app.test_request_context(
            "/onboarding/genres",
            method="POST",
            data={"priority_1": "1"},
        ):
            with (
                patch("app.routes.onboarding.current_user", self.user),
                patch.object(Genre, "query") as genre_query,
                patch.object(UserFavoriteGenre, "query") as favorite_query,
                patch.object(db.session, "add"),
                patch.object(db.session, "commit", side_effect=error),
                patch.object(db.session, "rollback") as rollback,
                patch.object(self.app.logger, "warning"),
            ):
                genre_query.order_by.return_value.all.return_value = [
                    SimpleNamespace(id=1, name="드라마")
                ]
                favorite_query.filter_by.return_value.delete.return_value = 0

                _response, status = genres.__wrapped__()

        self.assertEqual(status, 409)
        rollback.assert_called_once_with()

    def test_account_ott_rejects_an_unknown_foreign_key(self):
        with self.app.test_request_context(
            "/me/ott-subscriptions",
            method="POST",
            data={"provider_id": "999"},
        ):
            with (
                patch("app.routes.account.current_user", self.user),
                patch.object(db.session, "query") as query,
                patch.object(db.session, "commit") as commit,
            ):
                query.return_value.filter_by.return_value.all.return_value = [(1,)]

                response = update_ott_subscriptions.__wrapped__()

        self.assertEqual(response.status_code, 302)
        commit.assert_not_called()

    def test_account_ott_conflict_rolls_back(self):
        error = IntegrityError("INSERT", {}, Exception("duplicate"))
        with self.app.test_request_context(
            "/me/ott-subscriptions",
            method="POST",
            data={"provider_id": "1"},
        ):
            with (
                patch("app.routes.account.current_user", self.user),
                patch.object(db.session, "query") as query,
                patch.object(UserOTTSubscription, "query") as subscription_query,
                patch.object(db.session, "add"),
                patch.object(db.session, "commit", side_effect=error),
                patch.object(db.session, "rollback") as rollback,
                patch.object(self.app.logger, "warning"),
            ):
                query.return_value.filter_by.return_value.all.return_value = [(1,)]
                subscription_query.filter_by.return_value.all.return_value = []

                response = update_ott_subscriptions.__wrapped__()

        self.assertEqual(response.status_code, 302)
        rollback.assert_called_once_with()

    def test_wishlist_database_failure_returns_json_and_rolls_back(self):
        entry = SimpleNamespace(
            is_wishlisted=False,
            watch_status=None,
            started_at=None,
            watched_at=None,
            updated_at=None,
        )
        with self.app.test_request_context(
            "/wishlist/10",
            method="POST",
            json={"is_wishlisted": True},
        ):
            with (
                patch("app.routes.wishlist.current_user", self.user),
                patch("app.routes.wishlist.get_or_create_movie", return_value=SimpleNamespace(id="movie-id")),
                patch("app.routes.wishlist._get_or_create_entry", return_value=entry),
                patch.object(db.session, "commit", side_effect=SQLAlchemyError("unavailable")),
                patch.object(db.session, "rollback") as rollback,
                patch.object(self.app.logger, "exception"),
            ):
                response, status = upsert_wishlist.__wrapped__(10)

        self.assertEqual(status, 503)
        self.assertIn("저장하지 못했습니다", response.get_json()["message"])
        rollback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

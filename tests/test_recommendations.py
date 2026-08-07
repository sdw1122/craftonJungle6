import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask_login import UserMixin

from app import create_app
from app.services.recommendations import (
    AIRecommendationError,
    Candidate,
    OpenAIReranker,
    RecommendationService,
    UserPreferenceProfile,
    catalog_fingerprint,
    score_candidates,
    should_exclude_known_movie,
)
from app.services.movie_catalog import MovieCatalogSyncError, collect_popular_movies
from app.services.movie_catalog_query import MoviePage


class FakeAI:
    is_configured = False
    model = "rules-v1"


class FakeRecommendationService:
    def __init__(self):
        self.generated = None

    def get_cached(self, user_id, limit):
        return {
            "source": "empty",
            "model": None,
            "generated_at": None,
            "expires_at": None,
            "recommendations": [],
        }

    def generate(self, user_id, limit, force=False):
        self.generated = (user_id, limit, force)
        return {
            "source": "rules",
            "model": "rules-v1",
            "generated_at": "2026-08-06T00:00:00+00:00",
            "expires_at": "2026-08-07T00:00:00+00:00",
            "recommendations": [{"tmdb_id": 10, "title": "추천 영화"}],
        }


class LoggedInUser(UserMixin):
    id = "11111111-1111-1111-1111-111111111111"
    nickname = "정글"
    needs_onboarding = False


def make_profile(**overrides):
    values = {
        "favorite_genres": [("DRAMA", "드라마", 1)],
        "activity_genre_weights": {},
        "known_movies": {},
        "fingerprint": "profile-hash",
    }
    values.update(overrides)
    return UserPreferenceProfile(**values)


def make_candidate(tmdb_id, *, genres=None, watch_status=None, wishlisted=False):
    genre_codes = genres or ["DRAMA"]
    genre_names = {"DRAMA": "드라마", "ACTION": "액션", "THRILLER": "스릴러"}
    return Candidate(
        movie_id=f"movie-{tmdb_id}",
        tmdb_id=tmdb_id,
        title=f"영화 {tmdb_id}",
        original_title=f"Movie {tmdb_id}",
        overview="줄거리",
        release_date="2026-01-01",
        poster_url=None,
        genre_codes=genre_codes,
        genre_names=[genre_names[code] for code in genre_codes],
        is_wishlisted=wishlisted,
        watch_status=watch_status,
    )


class RecommendationScoringTests(unittest.TestCase):
    def test_favorite_genre_drives_database_candidate_score(self):
        profile = make_profile()
        drama = make_candidate(1, genres=["DRAMA"])
        unrelated = make_candidate(2, genres=["ACTION"])

        ranked = score_candidates([unrelated, drama], profile)

        self.assertEqual(ranked[0].tmdb_id, 1)
        self.assertAlmostEqual(drama.base_score, 0.65, places=6)
        self.assertEqual(unrelated.base_score, 0)

    def test_watching_and_wishlist_are_interest_signals(self):
        profile = make_profile()
        watching = make_candidate(1, watch_status="WATCHING")
        untouched = make_candidate(2)

        score_candidates([watching, untouched], profile)

        self.assertAlmostEqual(watching.base_score - untouched.base_score, 0.10, places=6)

    def test_activity_genre_weight_is_twenty_five_percent(self):
        profile = make_profile(
            favorite_genres=[],
            activity_genre_weights={"THRILLER": 1.0},
        )
        thriller = make_candidate(1, genres=["THRILLER"])

        score_candidates([thriller], profile)

        self.assertAlmostEqual(thriller.base_score, 0.25, places=6)

    def test_watched_movies_are_excluded(self):
        self.assertTrue(should_exclude_known_movie({"watch_status": "WATCHED"}))
        self.assertFalse(should_exclude_known_movie({"watch_status": "WATCHING"}))

    def test_reviewed_movies_are_treated_as_already_watched(self):
        self.assertTrue(should_exclude_known_movie({"has_review": True}))

    def test_catalog_fingerprint_changes_with_count_or_update_time(self):
        first = datetime(2026, 8, 6, tzinfo=timezone.utc)

        baseline = catalog_fingerprint(100, first)

        self.assertNotEqual(baseline, catalog_fingerprint(101, first))
        self.assertNotEqual(baseline, catalog_fingerprint(100, first + timedelta(seconds=1)))


class OpenAIRerankerTests(unittest.TestCase):
    def test_responses_api_uses_private_structured_contract(self):
        captured = {}

        class Responses:
            def parse(self, **kwargs):
                captured.update(kwargs)
                parsed = kwargs["text_format"](
                    recommendations=[
                        {"tmdb_id": 1, "ai_score": 0.9, "reason": "드라마 취향과 잘 맞아요."}
                    ]
                )
                return SimpleNamespace(output_parsed=parsed)

        class OpenAIStub:
            def __init__(self, **_kwargs):
                self.responses = Responses()

        reranker = OpenAIReranker("test-key", "gpt-5.6-luna", 20)
        with patch("openai.OpenAI", OpenAIStub):
            result = reranker.rerank(
                [make_candidate(1)],
                make_profile(),
                limit=10,
                safety_identifier="anonymous-user-hash",
            )

        self.assertEqual(result[1][0], 0.9)
        self.assertEqual(captured["model"], "gpt-5.6-luna")
        self.assertEqual(captured["reasoning"], {"effort": "low"})
        self.assertFalse(captured["store"])
        self.assertEqual(captured["safety_identifier"], "anonymous-user-hash")
        self.assertNotIn("nickname", captured["input"])
        self.assertNotIn("email", captured["input"])
        self.assertNotIn("subscribed_ott", captured["input"])

    def test_candidate_outside_whitelist_is_rejected(self):
        class Responses:
            def parse(self, **kwargs):
                parsed = kwargs["text_format"](
                    recommendations=[
                        {"tmdb_id": 999, "ai_score": 0.9, "reason": "허용되지 않은 영화"}
                    ]
                )
                return SimpleNamespace(output_parsed=parsed)

        class OpenAIStub:
            def __init__(self, **_kwargs):
                self.responses = Responses()

        with patch("openai.OpenAI", OpenAIStub):
            with self.assertRaises(AIRecommendationError):
                OpenAIReranker("test-key", "gpt-5.6-luna", 20).rerank(
                    [make_candidate(1)],
                    make_profile(),
                    limit=10,
                    safety_identifier="anonymous-user-hash",
                )


class MovieCatalogCollectionTests(unittest.TestCase):
    def test_collects_exactly_100_unique_non_adult_movies_across_pages(self):
        class FakeTMDB:
            def __init__(self):
                self.pages = []

            def get_popular_movies(self, page):
                self.pages.append(page)
                start = 1 if page == 1 else (page - 1) * 20
                results = [
                    {"id": movie_id, "title": f"영화 {movie_id}", "adult": False}
                    for movie_id in range(start, start + 20)
                ]
                if page == 1:
                    results[0]["adult"] = True
                return {"page": page, "total_pages": 6, "results": results}

        tmdb = FakeTMDB()
        movies = collect_popular_movies(tmdb, 100)

        self.assertEqual(len(movies), 100)
        self.assertEqual(len({movie["id"] for movie in movies}), 100)
        self.assertNotIn(1, {movie["id"] for movie in movies})
        self.assertEqual(tmdb.pages, [1, 2, 3, 4, 5, 6])

    def test_insufficient_tmdb_results_fail_before_persistence(self):
        class FakeTMDB:
            def get_popular_movies(self, page):
                return {
                    "page": page,
                    "total_pages": 1,
                    "results": [{"id": 1}, {"id": 2}],
                }

        with self.assertRaises(MovieCatalogSyncError):
            collect_popular_movies(FakeTMDB(), 100)

    def test_sync_cli_is_registered_with_limit_option(self):
        app = create_app({"TESTING": True})
        result = app.test_cli_runner().invoke(args=["sync-popular-movies", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--limit", result.output)


class RecommendationCacheTests(unittest.TestCase):
    def test_legacy_cache_without_catalog_fingerprint_is_invalidated(self):
        service = RecommendationService(FakeAI())
        service._load_profile = lambda _user_id: make_profile()
        service._catalog_fingerprint = lambda: "catalog-v1"
        service._latest_run = lambda _user_id: SimpleNamespace(
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            context={"profile_fingerprint": "profile-hash", "limit": 10},
        )

        payload = service.get_cached("user-id", 10)

        self.assertEqual(payload["source"], "empty")

    def test_recommendation_service_has_no_tmdb_dependency(self):
        service = RecommendationService(FakeAI())

        self.assertFalse(hasattr(service, "tmdb"))


class RecommendationRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "LOGIN_DISABLED": True})
        self.fake_service = FakeRecommendationService()
        self.app.extensions["recommendation_service"] = self.fake_service
        self.client = self.app.test_client()

    def test_get_returns_empty_contract(self):
        response = self.client.get("/api/recommendations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"], "empty")
        self.assertEqual(response.get_json()["recommendations"], [])

    def test_post_validates_inputs(self):
        invalid_limit = self.client.post("/api/recommendations", json={"limit": 21})
        invalid_force = self.client.post("/api/recommendations", json={"force": "yes"})
        invalid_body = self.client.post("/api/recommendations", json=["invalid"])

        self.assertEqual(invalid_limit.status_code, 400)
        self.assertEqual(invalid_force.status_code, 400)
        self.assertEqual(invalid_body.status_code, 400)

    def test_post_passes_force_and_limit_to_service(self):
        response = self.client.post(
            "/api/recommendations",
            json={"force": True, "limit": 7},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"], "rules")
        self.assertEqual(self.fake_service.generated, (None, 7, True))

    def test_login_is_required_by_default(self):
        app = create_app({"TESTING": True})
        response = app.test_client().get("/api/recommendations")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])


class RecommendationHomeTests(unittest.TestCase):
    def test_logged_in_home_contains_async_recommendation_section(self):
        app = create_app({"TESTING": True})
        app.login_manager._user_callback = lambda _user_id: LoggedInUser()
        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = LoggedInUser.id
            session["_fresh"] = True

        empty_page = MoviePage(movies=[], page=1, total_pages=0, total_results=0)
        with patch("app.routes.pages.list_catalog_movies", return_value=empty_page):
            response = client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("정글님을 위한 추천", html)
        self.assertIn("/api/recommendations", html)
        self.assertIn("js/recommendations.js", html)
        self.assertIn("추천받기", html)

    def test_home_recommendations_only_generate_after_button_click(self):
        script_path = Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "recommendations.js"
        script = script_path.read_text(encoding="utf-8")

        self.assertNotIn("load();", script)
        self.assertNotIn("data.getUrl", script)
        self.assertIn('refresh.addEventListener("click", () => generate(true));', script)
        self.assertIn('setState("empty");', script)


if __name__ == "__main__":
    unittest.main()

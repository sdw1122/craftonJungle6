import unittest
from unittest.mock import patch

from app import create_app
from app.ott_icons import OTT_ICONS, TMDB_PROVIDER_NAME_TO_CODE
from app.services.movie_catalog_query import MoviePage


class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def test_public_pages_render(self):
        for path in ("/login", "/signup", "/search"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_obsolete_search_api_is_removed(self):
        response = self.client.get("/api/search")

        self.assertEqual(response.status_code, 404)

    def test_movie_api_uses_the_database_catalog(self):
        page = MoviePage(
            movies=[{"tmdb_id": 1, "title": "기생충"}],
            page=1,
            total_pages=1,
            total_results=1,
        )
        with patch("app.routes.api.list_catalog_movies", return_value=page) as catalog:
            response = self.client.get("/api/movies/search?query=기생충&page=1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["movies"][0]["title"], "기생충")
        catalog.assert_called_once_with(page=1, query="기생충")

    def test_route_rules_are_not_duplicated(self):
        rules = [
            (rule.rule, tuple(sorted(rule.methods - {"HEAD", "OPTIONS"})))
            for rule in self.app.url_map.iter_rules()
        ]

        self.assertEqual(len(rules), len(set(rules)))

    def test_all_templates_compile(self):
        for template_name in self.app.jinja_env.list_templates():
            with self.subTest(template=template_name):
                self.app.jinja_env.get_template(template_name)

    def test_supported_ott_provider_mappings(self):
        self.assertEqual(TMDB_PROVIDER_NAME_TO_CODE["wavve"], "WAVVE")
        self.assertNotIn("COUPANG_PLAY", OTT_ICONS)
        self.assertNotIn("Coupang Play", TMDB_PROVIDER_NAME_TO_CODE)


if __name__ == "__main__":
    unittest.main()

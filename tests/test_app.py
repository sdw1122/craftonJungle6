import unittest
from unittest.mock import patch

from app import create_app
from app.services.movie_catalog_query import MoviePage


class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def test_public_pages_render(self):
        for path in ("/login", "/signup", "/search"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_search_api_has_the_expected_url(self):
        response = self.client.get("/api/search")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "success", "data": []})

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


if __name__ == "__main__":
    unittest.main()

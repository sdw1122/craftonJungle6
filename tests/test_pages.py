import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from app import create_app
from app.services.movie_catalog_query import MovieDetailRecord, MoviePage


POPULAR_MOVIES = [
    {
        "tmdb_id": 10,
        "title": "인기 영화",
        "original_title": "Popular Movie",
        "overview": "줄거리",
        "release_date": "2026-08-01",
        "poster_url": "https://image.example/poster.jpg",
    },
    {
        "tmdb_id": 20,
        "title": "포스터 없는 영화",
        "original_title": "No Poster",
        "overview": None,
        "release_date": None,
        "poster_url": None,
    },
]

DETAIL_PAYLOAD = {
    "tmdb_id": 10,
    "title": "상세 영화",
    "original_title": "Detail Movie",
    "overview": "상세 줄거리",
    "release_date": "2026-01-01",
    "runtime_minutes": 123,
    "original_language": "ko",
    "poster_url": "https://image.example/detail.jpg",
    "genres": [{"code": "DRAMA", "name": "드라마"}],
    "directors": [{"tmdb_id": 1, "name": "감독 이름"}],
    "cast": [
        {
            "tmdb_id": 2,
            "name": "배우 이름",
            "character_name": "주인공",
            "billing_order": 0,
        }
    ],
    "watch_providers": [{"name": "넷플릭스", "offer_type": "SUBSCRIPTION"}],
    "watch_provider_link": "https://example.com/providers",
}


class PageTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

        self.list_patcher = patch("app.routes.pages.list_catalog_movies")
        self.detail_patcher = patch("app.routes.pages.get_catalog_movie_record")
        self.list_catalog_movies = self.list_patcher.start()
        self.get_catalog_movie_record = self.detail_patcher.start()

        self.list_catalog_movies.return_value = MoviePage(
            movies=POPULAR_MOVIES,
            page=1,
            total_pages=3,
            total_results=42,
        )
        self.get_catalog_movie_record.return_value = MovieDetailRecord(
            movie=SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000010")),
            payload=DETAIL_PAYLOAD,
        )

    def tearDown(self):
        self.list_patcher.stop()
        self.detail_patcher.stop()

    def test_root_renders_movies_from_database_catalog(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.list_catalog_movies.assert_called_once_with(page=1, query="")
        self.assertIn("인기 영화", html)
        self.assertIn("/movies/10", html)
        self.assertIn("2026", html)
        self.assertIn("포스터 없음", html)

    def test_search_uses_database_query_and_preserves_pagination(self):
        self.list_catalog_movies.return_value = MoviePage(
            movies=[POPULAR_MOVIES[0]],
            page=2,
            total_pages=3,
            total_results=42,
        )

        response = self.client.get("/?query=기생충&page=2")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.list_catalog_movies.assert_called_once_with(page=2, query="기생충")
        self.assertIn('value="기생충"', html)
        self.assertIn("page=1", html)
        self.assertIn("page=3", html)

    def test_invalid_page_returns_400_without_catalog_query(self):
        response = self.client.get("/?page=501")

        self.assertEqual(response.status_code, 400)
        self.list_catalog_movies.assert_not_called()

    def test_detail_renders_database_movie_information(self):
        response = self.client.get("/movies/10")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.get_catalog_movie_record.assert_called_once_with(10)
        self.assertIn("상세 영화", html)
        self.assertIn("감독 이름", html)
        self.assertIn("배우 이름", html)
        self.assertIn("넷플릭스", html)
        self.assertGreaterEqual(html.count("disabled"), 8)

    def test_missing_database_movie_returns_404(self):
        self.get_catalog_movie_record.return_value = None

        response = self.client.get("/movies/999999")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 404)
        self.assertIn("동기화된 영화 정보를 찾을 수 없습니다.", html)


if __name__ == "__main__":
    unittest.main()

import unittest

from app import create_app
from app.services.tmdb import TMDBError


class FakeTMDBClient:
    is_configured = True

    def __init__(self):
        self.popular_page = None
        self.search_args = None

    def get_popular_movies(self, page=1):
        self.popular_page = page
        return {
            "page": page,
            "total_pages": 3,
            "total_results": 2,
            "results": [
                {
                    "id": 10,
                    "title": "인기 영화",
                    "original_title": "Popular Movie",
                    "overview": "줄거리",
                    "release_date": "2026-08-01",
                    "poster_path": "/poster.jpg",
                },
                {
                    "id": 20,
                    "title": "포스터 없는 영화",
                    "original_title": "No Poster",
                    "overview": "",
                    "release_date": "",
                    "poster_path": None,
                },
            ],
        }

    def search_movies(self, query, page=1):
        self.search_args = (query, page)
        return {
            "page": page,
            "total_pages": 4,
            "total_results": 1,
            "results": [
                {
                    "id": 496243,
                    "title": "기생충",
                    "original_title": "기생충",
                    "overview": "영화 줄거리",
                    "release_date": "2019-05-30",
                    "poster_path": "/parasite.jpg",
                }
            ],
        }

    def get_movie(self, tmdb_id):
        return {
            "id": tmdb_id,
            "title": "상세 영화",
            "original_title": "Detail Movie",
            "overview": "상세 줄거리",
            "release_date": "2026-01-01",
            "runtime": 123,
            "original_language": "ko",
            "poster_path": "/detail.jpg",
            "genres": [{"id": 18, "name": "드라마"}],
            "credits": {
                "crew": [
                    {"id": 1, "name": "감독 이름", "job": "Director"}
                ],
                "cast": [
                    {
                        "id": 2,
                        "name": "배우 이름",
                        "character": "주인공",
                        "order": 0,
                    }
                ],
            },
        }

    def get_watch_providers(self, tmdb_id):
        return {
            "results": {
                "KR": {
                    "link": "https://example.com/providers",
                    "flatrate": [
                        {
                            "provider_id": 8,
                            "provider_name": "넷플릭스",
                            "display_priority": 0,
                        }
                    ],
                }
            }
        }


class PageTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()
        self.fake_tmdb = FakeTMDBClient()
        self.original_tmdb = self.app.extensions["tmdb_client"]
        self.app.extensions["tmdb_client"] = self.fake_tmdb

    def tearDown(self):
        self.app.extensions["tmdb_client"] = self.original_tmdb

    def test_root_renders_popular_movies_and_fallbacks(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_tmdb.popular_page, 1)
        self.assertIn("인기 영화", html)
        self.assertIn('/movies/10', html)
        self.assertIn("2026", html)
        self.assertIn("포스터 없음", html)
        self.assertIn("개봉일 미정", html)

    def test_search_uses_query_and_preserves_pagination(self):
        response = self.client.get("/?query=기생충&page=2")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_tmdb.search_args, ("기생충", 2))
        self.assertIn('value="기생충"', html)
        self.assertIn("page=1", html)
        self.assertIn("page=3", html)
        self.assertIn('/movies/496243', html)

    def test_invalid_page_returns_400(self):
        response = self.client.get("/?page=501")

        self.assertEqual(response.status_code, 400)
        self.assertIn("page는 1부터 500 사이", response.get_data(as_text=True))

    def test_detail_renders_movie_information_and_disabled_actions(self):
        response = self.client.get("/movies/10")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("상세 영화", html)
        self.assertIn("감독 이름", html)
        self.assertIn("배우 이름", html)
        self.assertIn("넷플릭스", html)
        self.assertIn("찜", html)
        self.assertIn("보는 중", html)
        self.assertIn("봤어요", html)
        self.assertGreaterEqual(html.count("disabled"), 8)

    def test_detail_error_returns_tmdb_status_and_back_link(self):
        self.fake_tmdb.get_movie = lambda tmdb_id: (_ for _ in ()).throw(
            TMDBError("영화를 찾을 수 없습니다.", 404)
        )

        response = self.client.get("/movies/999999")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 404)
        self.assertIn("영화를 찾을 수 없습니다.", html)
        self.assertIn("영화 목록으로 돌아가기", html)


if __name__ == "__main__":
    unittest.main()

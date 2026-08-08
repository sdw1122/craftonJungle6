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
    "now_playing_rank": None,
    "is_streaming": True,
    "watch_providers": [{"name": "넷플릭스", "offer_type": "SUBSCRIPTION"}],
    "watch_provider_link": "https://example.com/providers",
}


class PageTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

        self.list_patcher = patch("app.routes.search.list_catalog_movies")
        self.detail_patcher = patch("app.routes.pages.get_catalog_movie_record")
        self.ranked_patcher = patch("app.routes.pages.list_ranked_movies")
        self.now_playing_patcher = patch("app.routes.pages.list_now_playing_movies")
        self.random_patcher = patch("app.routes.pages.list_random_movies")
        self.search_ranked_patcher = patch("app.routes.search.list_ranked_movies")
        self.ott_rankings_patcher = patch("app.routes.pages.list_ott_rankings")
        self.providers_patcher = patch("app.routes.pages.list_active_ott_providers")
        self.wishlisted_patcher = patch("app.routes.pages.list_wishlisted_movies")
        self.wishlisted_ids_patcher = patch("app.routes.pages.wishlisted_tmdb_ids")
        self.search_wishlisted_ids_patcher = patch(
            "app.routes.search.wishlisted_tmdb_ids"
        )
        self.list_catalog_movies = self.list_patcher.start()
        self.get_catalog_movie_record = self.detail_patcher.start()
        self.list_ranked_movies = self.ranked_patcher.start()
        self.list_now_playing_movies = self.now_playing_patcher.start()
        self.list_random_movies = self.random_patcher.start()
        self.search_list_ranked_movies = self.search_ranked_patcher.start()
        self.list_ott_rankings = self.ott_rankings_patcher.start()
        self.list_active_ott_providers = self.providers_patcher.start()
        self.list_wishlisted_movies = self.wishlisted_patcher.start()
        self.wishlisted_tmdb_ids = self.wishlisted_ids_patcher.start()
        self.search_wishlisted_tmdb_ids = self.search_wishlisted_ids_patcher.start()

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
        self.list_ranked_movies.return_value = POPULAR_MOVIES
        self.list_now_playing_movies.return_value = [POPULAR_MOVIES[0]]
        self.list_random_movies.return_value = POPULAR_MOVIES
        self.search_list_ranked_movies.return_value = POPULAR_MOVIES
        self.list_ott_rankings.return_value = [{
            "provider": SimpleNamespace(id=1, code="NETFLIX", name="넷플릭스"),
            "movies": [POPULAR_MOVIES[0]],
        }]
        self.list_active_ott_providers.return_value = [
            SimpleNamespace(id=1, code="NETFLIX", name="넷플릭스"),
            SimpleNamespace(id=2, code="TVING", name="티빙"),
        ]
        self.list_wishlisted_movies.return_value = []
        self.wishlisted_tmdb_ids.return_value = set()
        self.search_wishlisted_tmdb_ids.return_value = set()

    def tearDown(self):
        self.list_patcher.stop()
        self.detail_patcher.stop()
        self.ranked_patcher.stop()
        self.now_playing_patcher.stop()
        self.random_patcher.stop()
        self.search_ranked_patcher.stop()
        self.ott_rankings_patcher.stop()
        self.providers_patcher.stop()
        self.wishlisted_patcher.stop()
        self.wishlisted_ids_patcher.stop()
        self.search_wishlisted_ids_patcher.stop()

    def test_root_renders_database_ranking_carousel(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.list_catalog_movies.assert_not_called()
        self.list_ranked_movies.assert_called_once_with(limit=12)
        self.list_now_playing_movies.assert_called_once_with(limit=12)
        self.list_random_movies.assert_called_once_with(limit=50)
        self.list_ott_rankings.assert_called_once_with(limit=12)
        self.assertIn('role="tablist"', html)
        self.assertIn('data-ranking-tab="all"', html)
        self.assertIn('data-ranking-tab="subscriptions"', html)
        self.assertIn('data-ranking-tab="box-office"', html)
        self.assertIn('data-ranking-tab="provider-1"', html)
        self.assertIn("내 구독 OTT", html)
        self.assertIn("넷플릭스", html)
        self.assertIn("맞춤 랭킹", html)
        self.assertIn("내가 찜한 콘텐츠", html)
        self.assertIn("랜덤 영화", html)
        self.assertLess(html.index("내가 찜한 콘텐츠"), html.index("랜덤 영화"))
        self.assertIn('class="site-footer"', html)
        self.assertIn("TMDB · JustWatch 데이터 동기화 기준", html)
        self.assertIn("로그인하고 찜한 콘텐츠를 모아보세요", html)
        self.list_wishlisted_movies.assert_not_called()
        self.wishlisted_tmdb_ids.assert_not_called()
        self.assertIn("data-wishlist-toggle", html)
        self.assertIn("인기 영화", html)
        self.assertIn("/movies/10", html)
        self.assertIn('href="/rankings"', html)
        self.assertIn('action="/search"', html)
        self.assertGreaterEqual(html.count('href="/search"'), 1)

    def test_rankings_page_renders_all_movies_and_sidebar(self):
        response = self.client.get("/rankings")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.list_active_ott_providers.assert_called_once_with()
        self.list_ranked_movies.assert_called_once_with(limit=50)
        self.assertIn("전체 OTT 랭킹", html)
        self.assertIn('class="rankings-board"', html)
        self.assertIn("내 구독 OTT", html)
        self.assertIn("넷플릭스", html)
        self.assertIn('href="/rankings?ott=1"', html)
        self.assertIn("인기 영화", html)
        self.assertIn("data-wishlist-toggle", html)
        self.assertIn('src="/static/js/wishlist-toggle.js"', html)
        self.wishlisted_tmdb_ids.assert_not_called()

    def test_rankings_page_filters_selected_provider(self):
        response = self.client.get("/rankings?ott=2")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.list_ranked_movies.assert_called_once_with(limit=50, provider_ids=[2])
        self.assertIn("티빙 랭킹", html)
        self.assertIn(
            'class="rankings-category-link active" href="/rankings?ott=2"',
            html,
        )

    def test_rankings_page_renders_box_office_ranking(self):
        response = self.client.get("/rankings?ott=box-office")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.list_now_playing_movies.assert_called_once_with(limit=50)
        self.list_ranked_movies.assert_not_called()
        self.assertIn("박스오피스 랭킹", html)
        self.assertIn("TMDB 기준 한국 극장 상영작 인기순", html)
        self.assertIn(
            'class="rankings-category-link active" href="/rankings?ott=box-office"',
            html,
        )

    def test_guest_subscription_rankings_prompt_for_login(self):
        response = self.client.get("/rankings?ott=subscriptions")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.list_ranked_movies.assert_not_called()
        self.assertIn("로그인하고 내 구독 OTT 랭킹을 확인하세요", html)
        self.assertIn('href="/login"', html)

    def test_root_ranking_carousel_pages_twelve_movies_by_three(self):
        self.list_ott_rankings.return_value = []
        self.list_now_playing_movies.return_value = []
        self.list_ranked_movies.return_value = [
            {
                **POPULAR_MOVIES[0],
                "tmdb_id": 100 + index,
                "title": f"인기 영화 {index + 1}",
            }
            for index in range(12)
        ]

        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("전체 OTT TOP 12", html)
        self.assertIn("data-ranking-carousel-next", html)
        self.assertIn("data-ranking-carousel-prev", html)
        self.assertIn("1–3 / 12", html)
        self.assertNotIn(
            'data-ranking-carousel-prev aria-label="이전 콘텐츠 3개 보기" disabled',
            html,
        )
        self.assertIn("currentPage = (page + pageCount) % pageCount;", html)
        self.assertEqual(
            html.count('<article class="ranking-card ranking-card-with-bookmark" data-ranking-carousel-item'),
            12,
        )

    def test_search_uses_database_query_and_preserves_pagination(self):
        self.list_catalog_movies.return_value = MoviePage(
            movies=[POPULAR_MOVIES[0]],
            page=2,
            total_pages=3,
            total_results=42,
        )

        response = self.client.get("/search?query=기생충&page=2")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.list_catalog_movies.assert_called_once_with(page=2, query="기생충")
        self.assertIn('value="기생충"', html)
        self.assertIn("page=1", html)
        self.assertIn("page=3", html)
        self.assertIn("data-wishlist-toggle", html)
        self.assertIn('class="ranking-bookmark-button search-bookmark-button', html)
        self.assertIn('src="/static/js/wishlist-toggle.js"', html)
        self.search_list_ranked_movies.assert_not_called()

    def test_search_without_query_renders_popular_movies(self):
        response = self.client.get("/search")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.search_list_ranked_movies.assert_called_once_with(limit=50)
        self.list_catalog_movies.assert_not_called()
        self.assertIn("전체 인기 작품", html)
        self.assertIn("인기 영화", html)
        self.assertIn("data-wishlist-toggle", html)
        self.assertNotIn('aria-label="검색 결과 페이지"', html)

    def test_legacy_root_search_redirects_to_search_page(self):
        response = self.client.get("/?query=기생충&page=2")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/search?query=", response.headers["Location"])
        self.assertIn("page=2", response.headers["Location"])
        self.list_catalog_movies.assert_not_called()

    def test_invalid_page_returns_400_without_catalog_query(self):
        response = self.client.get("/search?query=기생충&page=501")

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

    def test_now_playing_detail_links_to_tmdb(self):
        payload = {
            **DETAIL_PAYLOAD,
            "now_playing_rank": 1,
            "watch_providers": [{
                "name": "박스오피스",
                "code": "BOX_OFFICE",
                "offer_type": "THEATRICAL",
                "content_url": "https://www.themoviedb.org/movie/10?language=ko-KR",
            }],
        }
        self.get_catalog_movie_record.return_value = MovieDetailRecord(
            movie=SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000010")),
            payload=payload,
        )

        response = self.client.get("/movies/10")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("극장", html)
        self.assertIn("박스오피스", html)
        self.assertIn("바로 보기", html)
        self.assertIn(
            'href="https://www.themoviedb.org/movie/10?language=ko-KR"',
            html,
        )

    def test_streaming_only_detail_shows_streaming_instead_of_unknown_date(self):
        payload = {
            **DETAIL_PAYLOAD,
            "release_date": None,
            "is_streaming": True,
        }
        self.get_catalog_movie_record.return_value = MovieDetailRecord(
            movie=SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000010")),
            payload=payload,
        )

        response = self.client.get("/movies/10")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('<span class="detail-tag">스트리밍</span>', html)

    def test_missing_database_movie_returns_404(self):
        self.get_catalog_movie_record.return_value = None

        response = self.client.get("/movies/999999")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 404)
        self.assertIn("동기화된 영화 정보를 찾을 수 없습니다.", html)


if __name__ == "__main__":
    unittest.main()

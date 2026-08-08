from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class TMDBError(Exception):
    message: str
    status_code: int = 502

    def __str__(self) -> str:
        return self.message


class TMDBClient:
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p"

    def __init__(self, access_token: str | None, timeout: float = 10.0):
        self.access_token = (access_token or "").strip()
        self.timeout = timeout
        self.session = requests.Session()

        if self.access_token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
            })

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token)

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        if not self.is_configured:
            raise TMDBError("TMDB_ACCESS_TOKEN이 설정되지 않았습니다.", 503)

        try:
            response = self.session.get(
                f"{self.BASE_URL}{path}",
                params=params,
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise TMDBError("TMDB 요청 시간이 초과되었습니다.", 504) from exc
        except requests.RequestException as exc:
            raise TMDBError("TMDB 서버에 연결할 수 없습니다.", 502) from exc

        if response.status_code == 401:
            raise TMDBError("TMDB 인증 토큰이 올바르지 않습니다.", 502)
        if response.status_code == 404:
            raise TMDBError("TMDB에서 콘텐츠를 찾을 수 없습니다.", 404)
        if response.status_code == 429:
            raise TMDBError("TMDB 요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.", 503)

        try:
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            raise TMDBError("TMDB API 요청에 실패했습니다.", 502) from exc
        except ValueError as exc:
            raise TMDBError("TMDB가 올바르지 않은 응답을 반환했습니다.", 502) from exc

    def search_movies(self, query: str, page: int = 1) -> dict[str, Any]:
        return self._get(
            "/search/movie",
            query=query,
            language="ko-KR",
            include_adult="false",
            page=page,
        )

    def search_by_person(self, query: str, page: int = 1) -> dict:
        """
        배우나 감독 이름으로 검색하여 해당 인물이 참여한 영화 목록을 반환
        """
        
        # 파라미터(**params) 형태로 query와 language를 깔끔하게 전달
        person_search_data = self._get(
            "/search/person", 
            query=query, 
            language="ko-KR", 
            page=1
        )
        
        # 검색된 인물이 없으면 빈 결과 반환
        if not person_search_data.get("results"):
            return {"results": [], "page": 1, "total_pages": 0, "total_results": 0}

        # 2. 가장 정확도가 높은 첫 번째 인물의 고유 ID 추출
        person_id = person_search_data["results"][0]["id"]

        # 3. 해당 인물의 영화 참여 목록 가져오기
        credits_data = self._get(
            f"/person/{person_id}/movie_credits", 
            language="ko-KR"
        )

        # 4. 배우로 출연한 영화와 감독/스태프로 참여한 영화 합치기
        all_movies = credits_data.get("cast", []) + credits_data.get("crew", [])

        # 5. 중복 영화 제거 및 인기도 순으로 정렬
        unique_movies = {movie["id"]: movie for movie in all_movies}.values()
        sorted_movies = sorted(unique_movies, key=lambda x: x.get("popularity", 0), reverse=True)

        # 6. 기존 검색 결과와 동일한 형태로 반환
        return {
            "results": list(sorted_movies),
            "page": 1,
            "total_pages": 1,
            "total_results": len(sorted_movies)
        }
    
    def get_popular_movies(self, page: int = 1) -> dict[str, Any]:
        return self._get(
            "/movie/popular",
            language="ko-KR",
            region="KR",
            page=page,
        )

    def get_now_playing_movies(self, page: int = 1) -> dict[str, Any]:
        return self._get(
            "/movie/now_playing",
            language="ko-KR",
            region="KR",
            page=page,
        )

    def discover_movies(
        self,
        *,
        page: int = 1,
        genre_ids: list[int] | None = None,
        watch_provider_id: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "language": "ko-KR",
            "region": "KR",
            "include_adult": "false",
            "include_video": "false",
            "sort_by": "popularity.desc",
            "page": page,
        }
        if genre_ids:
            params["with_genres"] = "|".join(str(genre_id) for genre_id in genre_ids)
        if watch_provider_id is not None:
            params.update({
                "watch_region": "KR",
                "with_watch_monetization_types": "flatrate",
                "with_watch_providers": str(watch_provider_id),
            })
        return self._get("/discover/movie", **params)

    def get_movie_watch_providers_catalog(self) -> dict[str, Any]:
        return self._get(
            "/watch/providers/movie",
            language="ko-KR",
            watch_region="KR",
        )

    def get_movie(self, tmdb_id: int) -> dict[str, Any]:
        return self._get(
            f"/movie/{tmdb_id}",
            language="ko-KR",
            append_to_response="credits,release_dates",
        )

    def get_watch_providers(self, tmdb_id: int) -> dict[str, Any]:
        return self._get(f"/movie/{tmdb_id}/watch/providers")

    @classmethod
    def image_url(cls, path: str | None, size: str = "w500") -> str | None:
        if not path:
            return None
        return f"{cls.IMAGE_BASE_URL}/{size}{path}"


def normalize_movie_detail(
    movie: dict[str, Any],
    provider_response: dict[str, Any],
) -> dict[str, Any]:
    credits = movie.get("credits") or {}
    cast = sorted(credits.get("cast") or [], key=lambda item: item.get("order", 9999))
    directors = [
        person
        for person in credits.get("crew") or []
        if person.get("job") == "Director"
    ]

    kr_release_results = [
        result
        for result in (movie.get("release_dates") or {}).get("results") or []
        if result.get("iso_3166_1") == "KR"
    ]
    kr_release_dates = [
        release
        for result in kr_release_results
        for release in result.get("release_dates") or []
    ]
    kr_release_date = None
    for release_type in (3, 2):
        theatrical_dates = sorted(
            release["release_date"].split("T", 1)[0]
            for release in kr_release_dates
            if release.get("type") == release_type and release.get("release_date")
        )
        if theatrical_dates:
            kr_release_date = theatrical_dates[0]
            break

    kr_providers = (provider_response.get("results") or {}).get("KR") or {}
    provider_groups = {
        "flatrate": "SUBSCRIPTION",
        "free": "FREE",
        "ads": "ADS",
        "rent": "RENT",
        "buy": "BUY",
    }
    watch_providers: list[dict[str, Any]] = []

    for tmdb_group, offer_type in provider_groups.items():
        for provider in kr_providers.get(tmdb_group) or []:
            watch_providers.append({
                "tmdb_provider_id": provider.get("provider_id"),
                "name": provider.get("provider_name"),
                "offer_type": offer_type,
                "display_priority": provider.get("display_priority"),
            })

    return {
        "tmdb_id": movie["id"],
        "title": movie.get("title"),
        "original_title": movie.get("original_title"),
        "overview": movie.get("overview"),
        "release_date": kr_release_date,
        "runtime_minutes": movie.get("runtime"),
        "original_language": movie.get("original_language"),
        "poster_url": TMDBClient.image_url(movie.get("poster_path")),
        "backdrop_url": TMDBClient.image_url(movie.get("backdrop_path"), "w1280"),
        "genres": [
            {"tmdb_id": genre.get("id"), "name": genre.get("name")}
            for genre in movie.get("genres") or []
        ],
        "directors": [
            {"tmdb_id": person.get("id"), "name": person.get("name")}
            for person in directors
        ],
        "cast": [
            {
                "tmdb_id": person.get("id"),
                "name": person.get("name"),
                "character_name": person.get("character"),
                "billing_order": person.get("order"),
            }
            for person in cast[:20]
        ],
        "watch_providers": watch_providers,
        "watch_provider_link": kr_providers.get("link"),
    }



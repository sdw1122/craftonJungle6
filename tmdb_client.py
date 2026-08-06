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

    def get_movie(self, tmdb_id: int) -> dict[str, Any]:
        return self._get(
            f"/movie/{tmdb_id}",
            language="ko-KR",
            append_to_response="credits",
        )

    def get_watch_providers(self, tmdb_id: int) -> dict[str, Any]:
        return self._get(f"/movie/{tmdb_id}/watch/providers")

    @classmethod
    def image_url(cls, path: str | None, size: str = "w500") -> str | None:
        if not path:
            return None
        return f"{cls.IMAGE_BASE_URL}/{size}{path}"


def normalize_search_movie(movie: dict[str, Any]) -> dict[str, Any]:
    return {
        "tmdb_id": movie["id"],
        "title": movie.get("title"),
        "original_title": movie.get("original_title"),
        "overview": movie.get("overview"),
        "release_date": movie.get("release_date") or None,
        "poster_url": TMDBClient.image_url(movie.get("poster_path")),
    }


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
        "release_date": movie.get("release_date") or None,
        "runtime_minutes": movie.get("runtime"),
        "original_language": movie.get("original_language"),
        "poster_url": TMDBClient.image_url(movie.get("poster_path")),
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

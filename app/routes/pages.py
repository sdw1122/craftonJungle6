from flask import Blueprint, render_template, request
from flask_login import current_user

from ..models import MovieReview, UserMovieLibrary
from ..ott_icons import DEFAULT_OTT_ICON, OTT_ICONS
from ..services.movie_catalog_query import (
    active_subscription_provider_ids,
    get_catalog_movie_record,
    list_active_ott_providers,
    list_catalog_movies,
    list_ott_rankings,
    list_personalized_movies,
    list_ranked_movies,
    list_wishlisted_movies,
)


pages_blueprint = Blueprint("pages", __name__)


@pages_blueprint.get("/")
def index():
    query = request.args.get("query", "").strip()
    page = request.args.get("page", default=1, type=int)

    if page is None or page < 1 or page > 500:
        return render_template(
            "index.html",
            movies=[],
            query=query,
            page=1,
            total_pages=0,
            total_results=0,
            error_message="page는 1부터 500 사이여야 합니다.",
        ), 400

    if not query:
        user_id = None
        subscription_provider_ids = []
        personalized_movies = []
        wishlisted_movies = []
        if current_user.is_authenticated:
            user_id = getattr(current_user, "id", None) or current_user.get_id()
            subscription_provider_ids = active_subscription_provider_ids(user_id)
            personalized_movies = list_personalized_movies(user_id=user_id, limit=3)
            wishlisted_movies = list_wishlisted_movies(user_id=user_id, limit=12)

        all_movies = list_ranked_movies(limit=12)
        subscription_movies = (
            list_ranked_movies(limit=12, provider_ids=subscription_provider_ids)
            if subscription_provider_ids
            else []
        )
        ott_rankings = list_ott_rankings(limit=12)
        ranking_tabs = [
            {
                "key": "all",
                "label": "전체",
                "title": "전체 OTT TOP 12",
                "description": "모든 OTT의 동기화된 인기 순위를 합산한 결과예요.",
                "movies": all_movies,
                "empty_message": "동기화된 인기 영화가 없습니다. 먼저 영화 동기화를 실행해주세요.",
                "icon": None,
                "requires_login": False,
                "requires_subscription": False,
            },
            {
                "key": "subscriptions",
                "label": "내 구독 OTT",
                "title": "내 구독 OTT TOP 12",
                "description": "내가 구독 중인 서비스에서 볼 수 있는 인기 작품이에요.",
                "movies": subscription_movies,
                "empty_message": "구독 중인 OTT에서 제공하는 영화가 아직 없습니다.",
                "icon": {"text": "MY", "color": "#7657d8"},
                "requires_login": not current_user.is_authenticated,
                "requires_subscription": current_user.is_authenticated and not subscription_provider_ids,
            },
        ]
        for ranking in ott_rankings:
            provider = ranking["provider"]
            ranking_tabs.append({
                "key": f"provider-{provider.id}",
                "label": provider.name,
                "title": f"{provider.name} TOP 12",
                "description": f"{provider.name}에서 볼 수 있는 인기 작품이에요.",
                "movies": ranking["movies"],
                "empty_message": f"{provider.name} 제공 정보가 있는 영화가 아직 없습니다.",
                "icon": OTT_ICONS.get(provider.code, DEFAULT_OTT_ICON),
                "requires_login": False,
                "requires_subscription": False,
            })

        return render_template(
            "index.html",
            home_mode=True,
            query="",
            ranking_tabs=ranking_tabs,
            personalized_movies=personalized_movies,
            wishlisted_movies=wishlisted_movies,
            ott_icons=OTT_ICONS,
            default_ott_icon=DEFAULT_OTT_ICON,
        )

    result = list_catalog_movies(page=page, query=query)

    return render_template(
        "index.html",
        home_mode=False,
        movies=result.movies,
        query=query,
        page=result.page,
        total_pages=result.total_pages,
        total_results=result.total_results,
        error_message=None,
    )


@pages_blueprint.get("/rankings")
def rankings():
    providers = list_active_ott_providers()
    selected_ott = request.args.get("ott", "all").strip().lower()
    selected_provider = None
    requires_login = False
    requires_subscription = False

    if selected_ott == "subscriptions":
        ranking_title = "내 구독 OTT 랭킹"
        ranking_description = "구독 중인 OTT에서 지금 볼 수 있는 인기 작품을 한곳에 모았어요."
        if current_user.is_authenticated:
            user_id = getattr(current_user, "id", None) or current_user.get_id()
            provider_ids = active_subscription_provider_ids(user_id)
            requires_subscription = not provider_ids
            movies = (
                list_ranked_movies(limit=50, provider_ids=provider_ids)
                if provider_ids
                else []
            )
        else:
            requires_login = True
            movies = []
    elif selected_ott.isdigit():
        provider_id = int(selected_ott)
        selected_provider = next(
            (provider for provider in providers if provider.id == provider_id),
            None,
        )
        if selected_provider is not None:
            ranking_title = f"{selected_provider.name} 랭킹"
            ranking_description = f"{selected_provider.name}에서 볼 수 있는 인기 작품 순위예요."
            movies = list_ranked_movies(limit=50, provider_ids=[selected_provider.id])
        else:
            selected_ott = "all"
            ranking_title = "전체 OTT 랭킹"
            ranking_description = "모든 OTT의 동기화된 인기 작품을 순위대로 확인하세요."
            movies = list_ranked_movies(limit=50)
    else:
        selected_ott = "all"
        ranking_title = "전체 OTT 랭킹"
        ranking_description = "모든 OTT의 동기화된 인기 작품을 순위대로 확인하세요."
        movies = list_ranked_movies(limit=50)

    return render_template(
        "rankings.html",
        providers=providers,
        selected_ott=selected_ott,
        selected_provider=selected_provider,
        ranking_title=ranking_title,
        ranking_description=ranking_description,
        movies=movies,
        requires_login=requires_login,
        requires_subscription=requires_subscription,
        ott_icons=OTT_ICONS,
        default_ott_icon=DEFAULT_OTT_ICON,
    )


@pages_blueprint.get("/movies/<int:tmdb_id>")
def movie_detail(tmdb_id: int):
    detail = get_catalog_movie_record(tmdb_id)
    if detail is None:
        return render_template(
            "movies/error.html",
            status_code=404,
            message="동기화된 영화 정보를 찾을 수 없습니다.",
        ), 404

    normalized = detail.payload
    local_movie = detail.movie

    reviews = (
        MovieReview.query
        .filter_by(movie_id=local_movie.id)
        .filter(MovieReview.deleted_at.is_(None))
        .order_by(MovieReview.created_at.desc())
        .all()
    )

    library_status = None
    my_review = None
    if current_user.is_authenticated:
        entry = UserMovieLibrary.query.filter_by(
            user_id=current_user.id, movie_id=local_movie.id
        ).first()
        if entry is not None:
            library_status = {
                "is_wishlisted": entry.is_wishlisted,
                "watch_status": entry.watch_status,
            }
        review = next((r for r in reviews if r.user_id == current_user.id), None)
        if review is not None:
            my_review = {
                "rating": review.rating,
                "content": review.content,
                "contains_spoiler": review.contains_spoiler,
            }

    return render_template(
        "movies/movie_detail.html",
        movie=normalized,
        library_status=library_status,
        my_review=my_review,
        reviews=reviews,
    )


@pages_blueprint.get("/contact")
def contact():
   
    return render_template("contact.html")

@pages_blueprint.get("/settings")
def settings():
    return render_template("settings.html")
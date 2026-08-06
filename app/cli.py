import click
from flask.cli import with_appcontext

from .services.movie_catalog import MovieCatalogSyncError, MovieCatalogSyncService
from .services.tmdb import get_tmdb_client


@click.command("sync-popular-movies")
@click.option(
    "--limit",
    default=100,
    type=click.IntRange(1, 500),
    show_default=True,
    help="동기화할 TMDB 인기 영화 수",
)
@with_appcontext
def sync_popular_movies(limit: int) -> None:
    """TMDB 인기 영화를 기존 영화 카탈로그에 동기화합니다."""
    try:
        result = MovieCatalogSyncService(get_tmdb_client()).sync_popular(limit)
    except MovieCatalogSyncError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        "동기화 완료: "
        f"요청 {result.requested}편, "
        f"신규 {result.created}편, "
        f"갱신 {result.updated}편, "
        f"제목 {result.titles_synced}건, "
        f"장르 연결 {result.genre_links_synced}건"
    )

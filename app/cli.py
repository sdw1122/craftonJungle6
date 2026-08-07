import os

import click
from flask.cli import with_appcontext
from sqlalchemy.exc import SQLAlchemyError

from .extensions import db
from .services.movie_catalog import MovieCatalogSyncError, sync_popular_movie_catalog


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
        result = sync_popular_movie_catalog(
            access_token=os.getenv("TMDB_ACCESS_TOKEN"),
            limit=limit,
        )
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


@click.command("upgrade-movie-catalog-schema")
@with_appcontext
def upgrade_movie_catalog_schema() -> None:
    """기존 DB에 영화 카탈로그 동기화용 컬럼과 인덱스를 추가합니다."""
    try:
        db.session.execute(db.text(
            "ALTER TABLE movies ADD COLUMN IF NOT EXISTS popular_rank SMALLINT "
            "CHECK (popular_rank IS NULL OR popular_rank > 0)"
        ))
        db.session.execute(db.text(
            "ALTER TABLE movies ADD COLUMN IF NOT EXISTS backdrop_url TEXT"
        ))
        db.session.execute(db.text(
            "CREATE INDEX IF NOT EXISTS idx_movies_popular_rank "
            "ON movies (popular_rank) WHERE popular_rank IS NOT NULL"
        ))
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise click.ClickException("영화 카탈로그 DB 마이그레이션에 실패했습니다.") from exc

    click.echo("영화 카탈로그 DB 마이그레이션이 완료되었습니다.")

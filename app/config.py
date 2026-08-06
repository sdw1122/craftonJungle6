import os

from sqlalchemy import URL


def database_uri() -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=os.getenv("DB_USER", "flask_user"),
        password=os.getenv("DB_PASSWORD", "flask_password"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "flask_app"),
    )

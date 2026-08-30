from app.core.config import Settings


def test_common_postgresql_urls_use_installed_psycopg_driver():
    assert Settings(DATABASE_URL="postgresql://user:pass@db.example/app").DATABASE_URL == (
        "postgresql+psycopg://user:pass@db.example/app"
    )
    assert Settings(DATABASE_URL="postgres://user:pass@db.example/app").DATABASE_URL == (
        "postgresql+psycopg://user:pass@db.example/app"
    )


def test_explicit_psycopg_url_is_unchanged():
    database_url = "postgresql+psycopg://user:pass@db.example/app"
    assert Settings(DATABASE_URL=database_url).DATABASE_URL == database_url

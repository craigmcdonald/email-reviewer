import pytest

from app.database import _async_database_url


@pytest.mark.parametrize(
    "input_url, expected",
    [
        (
            "postgresql://user:pass@localhost:5432/db",
            "postgresql+asyncpg://user:pass@localhost:5432/db",
        ),
        (
            "postgresql://craig:@localhost:5432/email_reviewer",
            "postgresql+asyncpg://craig:@localhost:5432/email_reviewer",
        ),
        (
            "postgresql+psycopg2://user:pass@localhost/db",
            "postgresql+asyncpg://user:pass@localhost/db",
        ),
        (
            "postgresql+asyncpg://user:pass@localhost/db",
            "postgresql+asyncpg://user:pass@localhost/db",
        ),
        (
            "sqlite+aiosqlite:///test.db",
            "sqlite+aiosqlite:///test.db",
        ),
    ],
)
def test_async_database_url(input_url, expected):
    assert _async_database_url(input_url) == expected

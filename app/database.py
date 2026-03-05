from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _async_database_url(url: str) -> str:
    """Convert a database URL to use an async driver."""
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


_url = _async_database_url(settings.DATABASE_URL)
_engine_kwargs: dict = {}
if _url.startswith("postgresql"):
    _engine_kwargs["pool_timeout"] = 10
    _engine_kwargs["connect_args"] = {
        "timeout": 10,
        "command_timeout": 10,
        "server_settings": {"statement_timeout": "10000"},
    }
engine = create_async_engine(_url, **_engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
AsyncSessionLocal = async_session


async def get_db():
    async with async_session() as session:
        yield session

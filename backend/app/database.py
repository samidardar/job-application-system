from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


engine = create_async_engine(
    settings.database_url,
    # echo=True logs ALL SQL queries including data — NEVER in production
    # Only enable explicitly via SQLALCHEMY_ECHO env var for debugging
    echo=False,
    pool_pre_ping=True,           # Detect stale connections before use
    pool_size=10,                 # Base connection pool size
    max_overflow=20,              # Extra connections allowed under load
    pool_recycle=3600,            # Recycle connections after 1h (prevents stale conn errors)
    pool_timeout=30,              # Raise after 30s waiting for a connection
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

import redis.asyncio as aioredis
from app.config import settings

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url.replace("/0", "/1"), decode_responses=True)
    return _redis


async def add(jti: str, ttl_seconds: int) -> None:
    """Blacklist a token JTI until it expires."""
    r = _get_redis()
    await r.setex(f"blacklist:{jti}", ttl_seconds, "1")


async def is_blacklisted(jti: str) -> bool:
    """Return True if the token JTI has been revoked."""
    r = _get_redis()
    return await r.exists(f"blacklist:{jti}") == 1

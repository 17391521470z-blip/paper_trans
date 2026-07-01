from collections.abc import AsyncIterator

from redis.asyncio import Redis, from_url

from app.core.config import get_settings


settings = get_settings()


redis_client: Redis = from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
    max_connections=settings.redis_max_connections,
)


async def get_redis() -> AsyncIterator[Redis]:
    try:
        yield redis_client
    finally:
        pass

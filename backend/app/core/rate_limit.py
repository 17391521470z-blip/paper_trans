import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.redis_client import redis_client


def _is_whitelisted(path: str) -> bool:
    return any(
        path.startswith(p)
        for p in (
            "/api/v1/health",
            "/static/",
            "/docs",
            "/redoc",
            "/openapi.json",
        )
    )


class _MemoryRateLimiter:
    def __init__(self) -> None:
        self._store: dict[str, list[float]] = {}
        self._last_cleanup: float = time.time()
        self._cleanup_interval: float = 60.0

    def check(self, client_ip: str, window: int, max_count: int) -> bool:
        now = time.time()
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup(now)

        timestamps = self._store.get(client_ip, [])
        cutoff = now - window
        timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= max_count:
            self._store[client_ip] = timestamps
            return False

        timestamps.append(now)
        self._store[client_ip] = timestamps
        return True

    def _cleanup(self, now: float) -> None:
        self._last_cleanup = now
        cutoff = now - 86400
        expired = [k for k, v in self._store.items() if all(t < cutoff for t in v)]
        for k in expired:
            del self._store[k]
        for k in list(self._store.keys()):
            valid = [t for t in self._store[k] if t > cutoff]
            if valid:
                self._store[k] = valid
            else:
                del self._store[k]


_memory_limiter = _MemoryRateLimiter()

GENERAL_WINDOW = 86400
GENERAL_MAX = 200
AUTH_WINDOW = 60
AUTH_MAX = 50


async def _check_redis(client_ip: str, window: int, max_count: int) -> bool:
    is_auth = window == AUTH_WINDOW
    prefix = "ratelimit:auth:" if is_auth else "ratelimit:ip:"
    key = f"{prefix}{client_ip}"
    now = time.time()

    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zcard(key)
    results = await pipe.execute()
    count = results[1]

    if count >= max_count:
        return False

    pipe = redis_client.pipeline()
    pipe.zadd(key, {str(now): now})
    pipe.expire(key, window)
    await pipe.execute()
    return True


async def rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path

    if _is_whitelisted(path):
        return await call_next(request)

    is_auth = "/auth/" in path
    window = AUTH_WINDOW if is_auth else GENERAL_WINDOW
    max_count = AUTH_MAX if is_auth else GENERAL_MAX

    try:
        allowed = await _check_redis(client_ip, window, max_count)
    except Exception:
        allowed = _memory_limiter.check(client_ip, window, max_count)

    if not allowed:
        return Response(
            status_code=429,
            content='{"code": "rate_limited", "message": "请求过于频繁，请稍后再试"}',
            media_type="application/json",
            headers={"Retry-After": str(window)},
        )

    return await call_next(request)

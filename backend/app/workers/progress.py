from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from typing import Any, AsyncIterator

from app.core.logging import get_logger
from app.core.redis_client import redis_client


logger = get_logger(__name__)


def channel_name(task_id: str | uuid.UUID) -> str:
    return f"task:{task_id}"


_redis_available: bool | None = None


async def _check_redis() -> bool:
    global _redis_available
    if _redis_available is False:
        return False
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=0.5)
        _redis_available = True
        return True
    except Exception:
        _redis_available = False
        return False


_in_memory_subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
_in_memory_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
_in_memory_lock = asyncio.Lock()


async def _in_memory_publish(task_id: str | uuid.UUID, payload: dict[str, Any]) -> int:
    channel = channel_name(task_id)
    async with _in_memory_lock:
        history = _in_memory_history.get(channel)
        if history is not None:
            history.append(payload)
            if len(history) > 200:
                del history[: len(history) - 200]
        subs = list(_in_memory_subscribers.get(channel, ()))
    delivered = 0
    for q in subs:
        try:
            q.put_nowait(payload)
            delivered += 1
        except asyncio.QueueFull:
            pass
    return delivered


async def _in_memory_subscribe(
    task_id: str | uuid.UUID,
    *,
    snapshot: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    channel = channel_name(task_id)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=512)
    async with _in_memory_lock:
        _in_memory_subscribers[channel].add(queue)
        replay = list(_in_memory_history.get(channel, ()))
    try:
        for past in replay:
            yield past
        if snapshot:
            yield snapshot
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            yield event
    finally:
        async with _in_memory_lock:
            subs = _in_memory_subscribers.get(channel)
            if subs is not None:
                subs.discard(queue)
                if not subs:
                    _in_memory_subscribers.pop(channel, None)


async def publish_progress(
    task_id: str | uuid.UUID,
    progress: int,
    *,
    status: str | None = None,
    message: str | None = None,
    extra: dict[str, Any] | None = None,
) -> int:
    payload: dict[str, Any] = {
        "task_id": str(task_id),
        "progress": int(progress),
    }
    if status is not None:
        payload["status"] = status
    if message is not None:
        payload["message"] = message
    if extra:
        payload.update(extra)
    try:
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.warning("progress.publish.encode_failed", error=str(exc))
        return 0

    if await _check_redis():
        try:
            delivered = await redis_client.publish(channel_name(task_id), encoded)
            if isinstance(delivered, int):
                return delivered
        except Exception as exc:
            logger.warning(
                "progress.publish.redis_failed_fallback_memory",
                task_id=str(task_id),
                error=str(exc),
            )

    return await _in_memory_publish(task_id, payload)


async def store_progress_snapshot(
    task_id: str | uuid.UUID,
    payload: dict[str, Any],
    *,
    ttl_seconds: int = 86400,
) -> None:
    key = f"progress:{task_id}"
    try:
        await redis_client.set(key, json.dumps(payload, default=str), ex=ttl_seconds)
    except Exception as exc:
        logger.warning(
            "progress.snapshot.failed",
            task_id=str(task_id),
            error=str(exc),
        )


async def get_progress_snapshot(task_id: str | uuid.UUID) -> dict[str, Any] | None:
    key = f"progress:{task_id}"
    try:
        raw = await redis_client.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


async def subscribe_progress(
    task_id: str | uuid.UUID,
    *,
    snapshot: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> AsyncIterator[dict[str, Any]]:
    use_redis = await _check_redis()
    if use_redis:
        pubsub = redis_client.pubsub()
        channel = channel_name(task_id)
        try:
            await pubsub.subscribe(channel)
        except Exception as exc:
            logger.warning(
                "progress.subscribe.redis_failed_fallback_memory",
                task_id=str(task_id),
                error=str(exc),
            )
            use_redis = False
        else:
            try:
                if snapshot:
                    yield snapshot
                if timeout:
                    deadline = asyncio.get_event_loop().time() + timeout
                else:
                    deadline = None
                while True:
                    if deadline is not None and asyncio.get_event_loop().time() > deadline:
                        break
                    try:
                        msg = await pubsub.get_message(
                            ignore_subscribe_messages=True,
                            timeout=1.0,
                        )
                    except asyncio.CancelledError:
                        break
                    except Exception as exc:
                        logger.warning(
                            "progress.subscribe.error_fallback_memory",
                            task_id=str(task_id),
                            error=str(exc),
                        )
                        break
                    if not msg:
                        continue
                    if msg.get("type") != "message":
                        continue
                    data = msg.get("data")
                    if isinstance(data, bytes):
                        try:
                            data = data.decode("utf-8")
                        except UnicodeDecodeError:
                            continue
                    if not isinstance(data, str):
                        continue
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        logger.warning(
                            "progress.subscribe.invalid_json",
                            task_id=str(task_id),
                        )
                return
            finally:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()
                except Exception:
                    pass

    async for event in _in_memory_subscribe(task_id, snapshot=snapshot):
        yield event


__all__ = [
    "channel_name",
    "publish_progress",
    "store_progress_snapshot",
    "get_progress_snapshot",
    "subscribe_progress",
]

"""Cache + short-lived workflow state (Redis, with an in-process fallback for demo mode)."""

from __future__ import annotations

import json
import time
from typing import Any, Protocol


class Cache(Protocol):
    name: str

    async def get_json(self, key: str) -> Any | None: ...
    async def set_json(self, key: str, value: Any, ttl_s: int) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def incr_window(self, key: str, window_s: int) -> int: ...
    async def ping(self) -> bool: ...


class MemoryCache:
    name = "memory"

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}
        self._counters: dict[str, tuple[float, int]] = {}

    async def get_json(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None or item[0] < time.time():
            self._data.pop(key, None)
            return None
        return json.loads(item[1])

    async def set_json(self, key: str, value: Any, ttl_s: int) -> None:
        self._data[key] = (time.time() + ttl_s, json.dumps(value, default=str))

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def incr_window(self, key: str, window_s: int) -> int:
        now = time.time()
        exp, n = self._counters.get(key, (now + window_s, 0))
        if exp < now:
            exp, n = now + window_s, 0
        self._counters[key] = (exp, n + 1)
        return n + 1

    async def ping(self) -> bool:
        return True


class RedisCache:
    name = "redis"

    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self.r = Redis.from_url(url, decode_responses=True, socket_timeout=2)

    async def get_json(self, key: str) -> Any | None:
        raw = await self.r.get(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: Any, ttl_s: int) -> None:
        await self.r.set(key, json.dumps(value, default=str), ex=ttl_s)

    async def delete(self, key: str) -> None:
        await self.r.delete(key)

    async def incr_window(self, key: str, window_s: int) -> int:
        pipe = self.r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_s, nx=True)
        n, _ = await pipe.execute()
        return int(n)

    async def ping(self) -> bool:
        try:
            return bool(await self.r.ping())
        except Exception:
            return False


def build_cache(url: str | None) -> Cache:
    return RedisCache(url) if url else MemoryCache()

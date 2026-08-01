"""Redis-backed production rate-limit policy with fail-closed semantics."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol, cast

from redis.asyncio import Redis

logger = logging.getLogger("boardtrace_api.rate_limit")


class RateLimitUnavailable(RuntimeError):
    pass


class CounterStore(Protocol):
    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None: ...

    async def get_ttl(self, key: str) -> int: ...

    async def block(self, key: str, seconds: int) -> None: ...


_HIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
local ttl = redis.call('TTL', KEYS[1])
if count > tonumber(ARGV[1]) then return ttl end
return 0
"""


class RedisCounterStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        try:
            operation = self._redis.eval(_HIT_SCRIPT, 1, key, str(limit), str(window_seconds))
            result = await cast(Awaitable[object], operation)
        except Exception as error:
            raise RateLimitUnavailable("shared rate-limit state is unavailable") from error
        retry_after = int(cast(int, result))
        return max(1, retry_after) if retry_after > 0 else None

    async def get_ttl(self, key: str) -> int:
        try:
            return max(0, int(await self._redis.ttl(key)))
        except Exception as error:
            raise RateLimitUnavailable("shared rate-limit state is unavailable") from error

    async def block(self, key: str, seconds: int) -> None:
        try:
            await self._redis.set(key, "1", ex=seconds)
        except Exception as error:
            raise RateLimitUnavailable("shared rate-limit state is unavailable") from error


@dataclass(frozen=True)
class Limit:
    category: str
    count: int
    window_seconds: int


AUTHENTICATED_USER = Limit("authenticated_user", 30, 60)
AUTHENTICATED_GLOBAL = Limit("authenticated_global", 120, 60)
ANALYSIS_START = Limit("analysis_start", 3, 600)
MANUAL_RETRY = Limit("manual_retry", 2, 900)
FAILED_LOGIN = Limit("failed_login", 10, 900)
HEALTH = Limit("health", 30, 60)
FAILED_LOGIN_BLOCK_SECONDS = 1800
REDIS_RETRY_AFTER_SECONDS = 60
LOG_RETENTION_DAYS = 7


def masked_identity(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]


async def enforce(store: CounterStore, limit: Limit, identity: str, endpoint: str) -> int | None:
    key = f"boardtrace:rl:{limit.category}:{identity}"
    retry_after = await store.hit(key, limit.count, limit.window_seconds)
    if retry_after is not None:
        logger.warning(
            "rate_limit_violated",
            extra={
                "masked_identity": masked_identity(identity),
                "endpoint": endpoint,
                "limit_category": limit.category,
                "retention_days": LOG_RETENTION_DAYS,
            },
        )
    return retry_after

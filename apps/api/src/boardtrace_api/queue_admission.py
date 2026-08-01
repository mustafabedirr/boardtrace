"""Atomic Redis admission policy for the bounded production analysis queue."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast

from redis.asyncio import Redis


class AdmissionOutcome(StrEnum):
    ACTIVE = "ACTIVE"
    WAITING = "WAITING"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    USER_BUSY = "USER_BUSY"
    QUEUE_FULL = "QUEUE_FULL"
    TERMINAL = "TERMINAL"


@dataclass(frozen=True)
class QueueAdmission:
    outcome: AdmissionOutcome
    position: int | None = None
    deadline_at: int | None = None


class QueueAdmissionUnavailable(RuntimeError):
    pass


class QueueAdmissionController(Protocol):
    async def state(self, job_id: str) -> QueueAdmission | None: ...

    async def admit(self, job_id: str, user_id: str, consent: bool, now: int) -> QueueAdmission: ...

    async def cancel_waiting(self, job_id: str, user_id: str) -> bool: ...

    async def extend_wait(self, job_id: str, now: int) -> bool: ...

    async def expire_waiting(self, now: int) -> tuple[str, ...]: ...

    async def complete_active(self, job_id: str, user_id: str) -> str | None: ...


class ImmediateQueueAdmission:
    """Development/test adapter that preserves the durable outbox flow."""

    async def state(self, job_id: str) -> QueueAdmission | None:
        return None

    async def admit(self, job_id: str, user_id: str, consent: bool, now: int) -> QueueAdmission:
        return QueueAdmission(AdmissionOutcome.ACTIVE)

    async def cancel_waiting(self, job_id: str, user_id: str) -> bool:
        return False

    async def extend_wait(self, job_id: str, now: int) -> bool:
        return False

    async def expire_waiting(self, now: int) -> tuple[str, ...]:
        return ()

    async def complete_active(self, job_id: str, user_id: str) -> str | None:
        return None


_ADMIT = r"""
local active, waiting, users = KEYS[1], KEYS[2], KEYS[3]
local deadlines, extended, sequence = KEYS[4], KEYS[5], KEYS[6]
local job, user, consent, now = ARGV[1], ARGV[2], ARGV[3], tonumber(ARGV[4])
if redis.call('HEXISTS', users, user) == 1 then return {'USER_BUSY', '0'} end
if redis.call('SCARD', active) < 2 then
  redis.call('SADD', active, job); redis.call('HSET', users, user, job); return {'ACTIVE', '0'}
end
if consent ~= '1' then return {'CONSENT_REQUIRED', '0'} end
if redis.call('ZCARD', waiting) >= 3 then return {'QUEUE_FULL', '0'} end
local score = redis.call('INCR', sequence)
redis.call('ZADD', waiting, score, job); redis.call('HSET', users, user, job)
redis.call('HSET', deadlines, job, now + 180); redis.call('HSET', extended, job, '0')
return {'WAITING', tostring(redis.call('ZRANK', waiting, job) + 1), tostring(now + 180)}
"""

_STATE = r"""
local active, waiting, deadlines = KEYS[1], KEYS[2], KEYS[3]
local job = ARGV[1]
if redis.call('SISMEMBER', active, job) == 1 then return {'ACTIVE', '0', '0'} end
local rank = redis.call('ZRANK', waiting, job)
if rank == false then return {} end
local deadline = redis.call('HGET', deadlines, job) or '0'
return {'WAITING', tostring(rank + 1), deadline}
"""

_CANCEL = r"""
local active, waiting, users, deadlines, extended = KEYS[1], KEYS[2], KEYS[3], KEYS[4], KEYS[5]
local job, user = ARGV[1], ARGV[2]
if redis.call('HGET', users, user) ~= job then return 0 end
local removed = redis.call('ZREM', waiting, job)
if removed == 1 then
  redis.call('HDEL', users, user)
  redis.call('HDEL', deadlines, job)
  redis.call('HDEL', extended, job)
end
return removed
"""

_EXTEND = r"""
local waiting, deadlines, extended = KEYS[1], KEYS[2], KEYS[3]
local job, now = ARGV[1], tonumber(ARGV[2])
if redis.call('ZSCORE', waiting, job) == false then return 0 end
if redis.call('HGET', extended, job) ~= '0' then return 0 end
local deadline = tonumber(redis.call('HGET', deadlines, job))
if deadline == nil or now > deadline then return 0 end
redis.call('HSET', deadlines, job, deadline + 180); redis.call('HSET', extended, job, '1')
return 1
"""

_SWEEP = r"""
local waiting, users, deadlines, extended = KEYS[1], KEYS[2], KEYS[3], KEYS[4]
local now = tonumber(ARGV[1]); local jobs = redis.call('ZRANGE', waiting, 0, -1); local expired = {}
for _, job in ipairs(jobs) do
  local deadline = tonumber(redis.call('HGET', deadlines, job))
  if deadline ~= nil and now >= deadline then
    redis.call('ZREM', waiting, job)
    redis.call('HDEL', deadlines, job)
    redis.call('HDEL', extended, job)
    local entries = redis.call('HGETALL', users)
    for index = 1, #entries, 2 do
      if entries[index + 1] == job then
        redis.call('HDEL', users, entries[index])
        break
      end
    end
    table.insert(expired, job)
  end
end
return expired
"""

_COMPLETE = r"""
local active, waiting, users, deadlines, extended = KEYS[1], KEYS[2], KEYS[3], KEYS[4], KEYS[5]
local job, user = ARGV[1], ARGV[2]
if redis.call('SREM', active, job) == 0 or redis.call('HGET', users, user) ~= job then return '' end
redis.call('HDEL', users, user)
local next = redis.call('ZRANGE', waiting, 0, 0)[1]
if next == nil then return '' end
redis.call('ZREM', waiting, next)
redis.call('SADD', active, next)
redis.call('HDEL', deadlines, next)
redis.call('HDEL', extended, next)
return next
"""


class RedisQueueAdmission:
    def __init__(self, redis: Redis, namespace: str = "boardtrace:admission") -> None:
        self._redis = redis
        self._keys = tuple(
            f"{namespace}:{name}"
            for name in ("active", "waiting", "users", "deadlines", "extended", "sequence")
        )

    async def state(self, job_id: str) -> QueueAdmission | None:
        raw = await self._eval(
            _STATE,
            3,
            self._keys[0],
            self._keys[1],
            self._keys[3],
            job_id,
        )
        values = cast(list[object], raw)
        return _admission(values) if values else None

    async def admit(self, job_id: str, user_id: str, consent: bool, now: int) -> QueueAdmission:
        raw = cast(
            list[object],
            await self._eval(_ADMIT, 6, *self._keys, job_id, user_id, "1" if consent else "0", now),
        )
        return _admission(raw)

    async def cancel_waiting(self, job_id: str, user_id: str) -> bool:
        return bool(await self._eval(_CANCEL, 5, *self._keys[:5], job_id, user_id))

    async def extend_wait(self, job_id: str, now: int) -> bool:
        return bool(
            await self._eval(_EXTEND, 3, self._keys[1], self._keys[3], self._keys[4], job_id, now)
        )

    async def expire_waiting(self, now: int) -> tuple[str, ...]:
        raw = cast(
            list[object],
            await self._eval(
                _SWEEP, 4, self._keys[1], self._keys[2], self._keys[3], self._keys[4], now
            ),
        )
        return tuple(_text(item) for item in raw)

    async def complete_active(self, job_id: str, user_id: str) -> str | None:
        raw = await self._eval(_COMPLETE, 5, *self._keys[:5], job_id, user_id)
        promoted = _text(raw)
        return promoted or None

    async def clear(self) -> None:
        try:
            operation = self._redis.delete(*self._keys)
            await cast(Awaitable[object], operation)
        except Exception as error:
            raise QueueAdmissionUnavailable("shared admission state is unavailable") from error

    async def _eval(self, script: str, numkeys: int, *keys_and_args: object) -> object:
        try:
            operation = self._redis.eval(script, numkeys, *(str(value) for value in keys_and_args))
            return await cast(Awaitable[object], operation)
        except Exception as error:
            raise QueueAdmissionUnavailable("shared admission state is unavailable") from error


def _text(value: object) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _admission(raw: list[object]) -> QueueAdmission:
    outcome = AdmissionOutcome(_text(raw[0]))
    position = int(_text(raw[1])) or None
    deadline = int(_text(raw[2])) or None if len(raw) > 2 else None
    return QueueAdmission(outcome, position, deadline)

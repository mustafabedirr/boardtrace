"""Exercise the production queue policy against the production-like Redis."""

import asyncio
import os

from boardtrace_api.queue_admission import AdmissionOutcome, RedisQueueAdmission
from redis.asyncio import Redis


async def validate() -> None:
    redis = Redis.from_url(os.environ["BOARDTRACE_REDIS_URL"], decode_responses=True)
    queue = RedisQueueAdmission(redis, "boardtrace:r5r1")
    try:
        await queue.clear()
        assert (await queue.admit("a", "u1", False, 0)).outcome is AdmissionOutcome.ACTIVE
        assert (await queue.admit("b", "u2", False, 0)).outcome is AdmissionOutcome.ACTIVE
        assert (await queue.admit("x", "ux", False, 0)).outcome is AdmissionOutcome.CONSENT_REQUIRED
        assert (await queue.admit("c", "u3", True, 0)).position == 1
        assert (await queue.admit("d", "u4", True, 0)).position == 2
        assert (await queue.admit("e", "u5", True, 0)).position == 3
        assert (await queue.admit("f", "u6", True, 0)).outcome is AdmissionOutcome.QUEUE_FULL
        assert (await queue.admit("again", "u3", True, 0)).outcome is AdmissionOutcome.USER_BUSY
        assert await queue.cancel_waiting("d", "u4")
        assert (await queue.admit("f", "u6", True, 0)).position == 3
        assert await queue.extend_wait("c", 179)
        assert not await queue.extend_wait("c", 180)
        assert set(await queue.expire_waiting(180)) == {"e", "f"}
        assert await queue.expire_waiting(359) == ()
        assert await queue.expire_waiting(360) == ("c",)
        assert await queue.complete_active("a", "u1") is None

        await queue.clear()
        assert (await queue.admit("p1", "p-u1", False, 0)).outcome is AdmissionOutcome.ACTIVE
        assert (await queue.admit("p2", "p-u2", False, 0)).outcome is AdmissionOutcome.ACTIVE
        assert (await queue.admit("p3", "p-u3", True, 0)).position == 1
        assert (await queue.admit("p4", "p-u4", True, 0)).position == 2
        assert await queue.complete_active("p1", "p-u1") == "p3"
        assert await queue.complete_active("p2", "p-u2") == "p4"
    finally:
        await queue.clear()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(validate())
    print("queue lifecycle validation passed")

"""Exercise API admission, durable outbox gating, cancellation and cleanup."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast
from uuid import UUID

from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.db.engine import create_database_engine
from boardtrace_api.db.session import create_session_factory
from boardtrace_api.models import AnalysisJob, AnalysisJobOutbox, Game, User
from boardtrace_api.provenance import canonical_source_checksum
from boardtrace_api.queue_admission import RedisQueueAdmission
from boardtrace_api.repositories.analysis_jobs import AnalysisJobRepository
from boardtrace_api.worker import _expire_waiting_jobs, _terminalize_external_failure
from redis.asyncio import Redis
from sqlalchemy import delete, func, select

BASE_URL = "http://127.0.0.1:8000/api/v1"


def _request(
    path: str, token: str, payload: dict[str, object] | None = None
) -> tuple[int, dict[str, object]]:
    body = json.dumps(payload).encode() if payload is not None else b""
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Host": "api",
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as error:
        return error.code, cast(dict[str, object], json.loads(error.read()))
    return response.status, cast(dict[str, object], json.loads(response.read()))


def _expect(
    status: int,
    payload: dict[str, object],
    expected_status: int,
    **fields: object,
) -> None:
    assert status == expected_status, (status, payload)
    for key, expected in fields.items():
        assert payload.get(key) == expected, (key, expected, payload)


async def _reset_admission(settings: Settings) -> None:
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    try:
        await RedisQueueAdmission(redis).clear()
    finally:
        await redis.aclose()


async def _create_users(settings: Settings) -> list[UUID]:
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            users = [
                User(
                    email=f"r5r2-{index}@example.test",
                    normalized_email=f"r5r2-{index}@example.test",
                    display_name=None,
                    password_hash=None,
                )
                for index in range(6)
            ]
            session.add_all(users)
            await session.commit()
            return [user.id for user in users]
    finally:
        await engine.dispose()


def _payload(index: int, *, consent: bool) -> dict[str, object]:
    source_game_id = f"r5r2-game-{index}"
    moves = ["e2e4"]
    return {
        "idempotency_key": sha256(source_game_id.encode()).hexdigest(),
        "platform": "lichess",
        "source_game_id": source_game_id,
        "acquisition_method": "browser_extension",
        "source_checksum": canonical_source_checksum("lichess", source_game_id, moves),
        "queue_consent": consent,
        "completed_at": datetime.now(UTC).isoformat(),
        "player_color": "UNKNOWN",
        "result": "UNKNOWN",
        "moves": moves,
    }


async def _verify_initial_gating(
    settings: Settings,
    responses: list[dict[str, object]],
    cancelled_id: str,
) -> None:
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            job_ids = [UUID(str(response["analysis_job_id"])) for response in responses]
            outbox_count = await session.scalar(
                select(func.count())
                .select_from(AnalysisJobOutbox)
                .where(AnalysisJobOutbox.analysis_job_id.in_(job_ids[:2]))
            )
            waiting_outbox_count = await session.scalar(
                select(func.count())
                .select_from(AnalysisJobOutbox)
                .where(AnalysisJobOutbox.analysis_job_id.in_(job_ids[2:]))
            )
            assert outbox_count == 2
            assert waiting_outbox_count == 0
            cancelled = await session.get(AnalysisJob, UUID(cancelled_id))
            assert cancelled is not None and cancelled.status.value == "CANCELLED"
            game = await session.get(Game, cancelled.game_id)
            assert game is not None
            assert game.platform == "deleted"
            assert game.source_game_id is None
            assert game.normalized_moves is None
            assert game.ingestion_payload_hash is None
    finally:
        await engine.dispose()


async def _verify_terminal_paths_and_cleanup(
    settings: Settings,
    user_ids: list[UUID],
    responses: list[dict[str, object]],
) -> None:
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    job_ids = [UUID(str(response["analysis_job_id"])) for response in responses]
    try:
        admission = RedisQueueAdmission(redis)
        first_promoted = await admission.state(str(job_ids[2]))
        second_promoted = await admission.state(str(job_ids[4]))
        assert first_promoted is not None and first_promoted.outcome.value == "ACTIVE"
        assert second_promoted is not None and second_promoted.outcome.value == "ACTIVE"
        assert await admission.state(str(job_ids[5])) is None
        async with factory() as session:
            jobs = [await session.get(AnalysisJob, job_id) for job_id in job_ids]
            assert all(job is not None for job in jobs)
            statuses = [job.status.value for job in jobs if job is not None]
            assert statuses == [
                "FAILED",
                "FAILED",
                "PENDING",
                "CANCELLED",
                "PENDING",
                "FAILED",
            ]
            assert jobs[0] is not None and jobs[0].last_error_code == "analysis_timeout"
            assert jobs[1] is not None and jobs[1].last_error_code == "worker_lost"
            assert jobs[5] is not None and jobs[5].last_error_code == "queue_wait_expired"
            assert not await AnalysisJobRepository(session).complete_job(
                job_ids[0], "late-worker", datetime.now(UTC), 1
            )
            outbox_count = await session.scalar(
                select(func.count())
                .select_from(AnalysisJobOutbox)
                .where(AnalysisJobOutbox.analysis_job_id.in_(job_ids))
            )
            assert outbox_count == 4
            for job in (jobs[0], jobs[1], jobs[3], jobs[5]):
                assert job is not None
                game = await session.get(Game, job.game_id)
                assert game is not None
                assert game.platform == "deleted"
                assert game.normalized_moves is None
                assert game.ingestion_payload_hash is None
            await session.execute(delete(User).where(User.id.in_(user_ids)))
            await session.commit()
        await admission.clear()
    finally:
        await redis.aclose()
        await engine.dispose()


async def validate() -> None:
    settings = Settings()
    await _reset_admission(settings)
    user_ids = await _create_users(settings)
    tokens = TokenService(settings)
    ingest_tokens = [
        tokens.issue_extension_token(user_id, f"r5r2-{index}", ("games:ingest",))
        for index, user_id in enumerate(user_ids)
    ]
    access_tokens = [tokens.issue_access_token(user_id) for user_id in user_ids]

    responses: list[dict[str, object]] = []
    for index in range(2):
        status, payload = _request(
            "/games/ingestions", ingest_tokens[index], _payload(index, consent=False)
        )
        _expect(status, payload, 201, queue_state="ACTIVE")
        responses.append(payload)

    status, consent_required = _request(
        "/games/ingestions", ingest_tokens[2], _payload(2, consent=False)
    )
    _expect(status, consent_required, 202, queue_state="CONSENT_REQUIRED")
    job3 = str(consent_required["analysis_job_id"])
    status, waiting1 = _request(f"/games/analysis-jobs/{job3}/queue-consent", access_tokens[2], {})
    _expect(status, waiting1, 200, queue_state="WAITING")
    assert waiting1["queue_position"] == 1
    responses.append(waiting1)

    for index, expected_position in ((3, 2), (4, 3)):
        status, waiting = _request(
            "/games/ingestions", ingest_tokens[index], _payload(index, consent=True)
        )
        _expect(status, waiting, 202, queue_position=expected_position)
        responses.append(waiting)

    status, full = _request("/games/ingestions", ingest_tokens[5], _payload(5, consent=True))
    _expect(status, full, 429)
    assert cast(dict[str, object], full["error"])["code"] == "analysis_queue_full"

    cancelled_id = str(responses[3]["analysis_job_id"])
    status, cancelled = _request(
        f"/games/analysis-jobs/{cancelled_id}/queue-cancel", access_tokens[3], {}
    )
    _expect(status, cancelled, 200, queue_state="CANCELLED")

    status, extended = _request(f"/games/analysis-jobs/{job3}/queue-extend", access_tokens[2], {})
    _expect(status, extended, 200, queue_state="WAITING")
    assert (
        cast(int, extended["queue_deadline_at"]) >= cast(int, waiting1["queue_deadline_at"]) + 180
    )

    status, waiting3 = _request("/games/ingestions", ingest_tokens[5], _payload(5, consent=True))
    _expect(status, waiting3, 202, queue_position=3)
    responses.append(waiting3)

    await _verify_initial_gating(settings, responses, cancelled_id)
    assert await _terminalize_external_failure(
        UUID(str(responses[0]["analysis_job_id"])), "analysis_timeout"
    )
    assert not await _terminalize_external_failure(
        UUID(str(responses[0]["analysis_job_id"])), "duplicate_timeout_callback"
    )
    assert await _terminalize_external_failure(
        UUID(str(responses[1]["analysis_job_id"])), "worker_lost"
    )
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    try:
        expired = await _expire_waiting_jobs(
            RedisQueueAdmission(redis), int(datetime.now(UTC).timestamp()) + 1000
        )
        assert expired == 1
    finally:
        await redis.aclose()
    await _verify_terminal_paths_and_cleanup(settings, user_ids, responses)


if __name__ == "__main__":
    asyncio.run(validate())
    print("integrated admission and terminal cleanup validation passed")

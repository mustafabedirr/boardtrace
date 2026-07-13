from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Protocol, cast
from uuid import uuid4

import pytest
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.api.v1.endpoints.auth import bearer, get_current_user
from boardtrace_api.auth.passwords import PasswordService
from boardtrace_api.auth.service import AuthenticationService
from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.core.errors import ApiError

pytestmark = [pytest.mark.database, pytest.mark.integration]


class _JwtEncoder(Protocol):
    def encode(self, payload: dict[str, object], key: str, algorithm: str) -> str: ...


jwt = cast(_JwtEncoder, import_module("jwt"))
TEST_JWT_SECRET = "test-jwt-signing-secret-with-adequate-length"
TEST_REFRESH_PEPPER = "test-refresh-token-pepper"


def auth_settings(*, jwt_signing_secret: str = TEST_JWT_SECRET) -> Settings:
    return Settings(
        jwt_signing_secret=jwt_signing_secret,
        refresh_token_pepper=TEST_REFRESH_PEPPER,
    )


def create_auth(session: AsyncSession) -> tuple[AuthenticationService, TokenService]:
    tokens = TokenService(auth_settings())
    return AuthenticationService(session, PasswordService(), tokens), tokens


def bearer_request(value: bytes | None) -> Request:
    headers = [] if value is None else [(b"authorization", value)]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def access_claims(subject: str) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "sub": subject,
        "iss": "boardtrace-api",
        "aud": "boardtrace-clients",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": str(uuid4()),
        "typ": "access",
    }


@pytest.mark.asyncio
async def test_current_user_resolves_an_unverified_user_without_mutating_database_state(
    auth_database_session: AsyncSession,
) -> None:
    auth, _ = create_auth(auth_database_session)
    user, pair = await auth.register(
        "current-user@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    resolved_credentials = await bearer(bearer_request(f"Bearer {pair.access_token}".encode()))
    assert resolved_credentials is not None

    resolved_user = await get_current_user(resolved_credentials, auth)

    assert resolved_user.id == user.id
    assert resolved_user.email_verified is False
    assert not auth_database_session.dirty


@pytest.mark.asyncio
async def test_bearer_parsing_and_missing_credentials_map_to_authentication_error(
    auth_database_session: AsyncSession,
) -> None:
    auth, _ = create_auth(auth_database_session)
    assert await bearer(bearer_request(None)) is None
    assert await bearer(bearer_request(b"Basic ignored")) is None
    assert await bearer(bearer_request(b"Bearer")) is None

    with pytest.raises(ApiError) as error:
        await get_current_user(None, auth)
    assert error.value.code == "authentication_required"
    assert error.value.status_code == 401
    assert error.value.message == "Authentication failed."


@pytest.mark.asyncio
async def test_current_user_rejects_invalid_access_token_claims_and_algorithms(
    auth_database_session: AsyncSession,
) -> None:
    auth, tokens = create_auth(auth_database_session)
    valid_claims = access_claims(str(uuid4()))
    missing_subject_claims = dict(valid_claims)
    del missing_subject_claims["sub"]
    expired_claims = dict(valid_claims)
    expired_claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    invalid_issuer_claims = dict(valid_claims)
    invalid_issuer_claims["iss"] = "unexpected-issuer"
    invalid_audience_claims = dict(valid_claims)
    invalid_audience_claims["aud"] = "unexpected-audience"
    malformed_subject_claims = dict(valid_claims)
    malformed_subject_claims["sub"] = "not-a-uuid"
    refresh_type_claims = dict(valid_claims)
    refresh_type_claims["typ"] = "refresh"
    invalid_tokens = [
        jwt.encode(valid_claims, "another-test-signing-secret-with-adequate-length", "HS256"),
        jwt.encode(expired_claims, TEST_JWT_SECRET, "HS256"),
        jwt.encode(
            valid_claims,
            "test-jwt-signing-secret-with-adequate-length-for-hs384",
            "HS384",
        ),
        jwt.encode(valid_claims, "", "none"),
        jwt.encode(invalid_issuer_claims, TEST_JWT_SECRET, "HS256"),
        jwt.encode(invalid_audience_claims, TEST_JWT_SECRET, "HS256"),
        jwt.encode(missing_subject_claims, TEST_JWT_SECRET, "HS256"),
        jwt.encode(malformed_subject_claims, TEST_JWT_SECRET, "HS256"),
        jwt.encode(refresh_type_claims, TEST_JWT_SECRET, "HS256"),
        tokens.new_refresh_token(),
    ]

    for token in invalid_tokens:
        with pytest.raises(ApiError) as error:
            await get_current_user(credentials(token), auth)
        assert error.value.code == "authentication_required"
        assert error.value.status_code == 401
        assert token not in error.value.message


@pytest.mark.asyncio
async def test_current_user_rejects_unknown_and_inactive_users(
    auth_database_session: AsyncSession,
) -> None:
    auth, tokens = create_auth(auth_database_session)
    unknown_user_token = tokens.issue_access_token(uuid4())
    with pytest.raises(ApiError) as unknown_error:
        await get_current_user(credentials(unknown_user_token), auth)
    assert unknown_error.value.code == "authentication_required"

    user, pair = await auth.register(
        "inactive-current-user@example.test",
        "correct-horse-battery-staple",
        None,
    )
    await auth_database_session.commit()
    user.is_active = False
    await auth_database_session.commit()

    with pytest.raises(ApiError) as inactive_error:
        await get_current_user(credentials(pair.access_token), auth)
    assert inactive_error.value.code == "authentication_required"

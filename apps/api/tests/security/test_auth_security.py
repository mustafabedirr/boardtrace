from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Protocol, cast
from uuid import UUID, uuid4

import httpx
import pytest

pytestmark = [pytest.mark.database, pytest.mark.integration]

AUTH_PREFIX = "/api/v1/auth"
PASSWORD = "correct-horse-battery-staple"
TEST_JWT_SECRET = "test-jwt-signing-secret-with-adequate-length"


class JwtEncoder(Protocol):
    def encode(self, payload: dict[str, object], key: str, algorithm: str) -> str: ...


jwt = cast(JwtEncoder, import_module("jwt"))


def access_claims(user_id: UUID) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "sub": str(user_id),
        "iss": "boardtrace-api",
        "aud": "boardtrace-clients",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": str(uuid4()),
        "typ": "access",
    }


def assert_bearer_authentication_error(response: httpx.Response, secret: str) -> None:
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.json()["error"]["code"] == "authentication_required"
    assert secret not in response.text


@pytest.mark.asyncio
async def test_protected_endpoints_reject_malformed_and_confused_bearer_tokens(
    auth_client: httpx.AsyncClient,
) -> None:
    registration = await auth_client.post(
        f"{AUTH_PREFIX}/register",
        json={"email": "api-security@example.com", "password": PASSWORD},
    )
    assert registration.status_code == 200
    valid_me = await auth_client.get(
        f"{AUTH_PREFIX}/me",
        headers={"Authorization": f"Bearer {registration.json()['access_token']}"},
    )
    assert valid_me.status_code == 200
    user_id = UUID(valid_me.json()["id"])
    claims = access_claims(user_id)
    wrong_issuer = dict(claims, iss="other-issuer")
    invalid_tokens = [
        "malformed-token",
        registration.json()["refresh_token"],
        jwt.encode(claims, "another-test-signing-secret-with-adequate-length", "HS256"),
        jwt.encode(
            claims,
            "test-jwt-signing-secret-with-adequate-length-for-hs384",
            "HS384",
        ),
        jwt.encode(claims, "", "none"),
        jwt.encode(wrong_issuer, TEST_JWT_SECRET, "HS256"),
    ]
    headers = [None, "Basic ignored", *[f"Bearer {token}" for token in invalid_tokens]]
    for authorization in headers:
        request_headers = {} if authorization is None else {"Authorization": authorization}
        response = await auth_client.get(f"{AUTH_PREFIX}/me", headers=request_headers)
        assert_bearer_authentication_error(response, PASSWORD)


@pytest.mark.asyncio
async def test_login_error_does_not_enable_user_enumeration_or_leak_credentials(
    auth_client: httpx.AsyncClient,
) -> None:
    email = "api-enumeration@example.com"
    registration = await auth_client.post(
        f"{AUTH_PREFIX}/register",
        json={"email": email, "password": PASSWORD},
    )
    assert registration.status_code == 200
    unknown = await auth_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": "missing-user@example.com", "password": PASSWORD},
    )
    incorrect_password = "incorrect-password-value"
    wrong_password = await auth_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": email, "password": incorrect_password},
    )

    for response in (unknown, wrong_password):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"
        assert response.json()["error"]["message"] == "Authentication failed."
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert PASSWORD not in response.text
        assert incorrect_password not in response.text
    assert unknown.json()["error"]["message"] == wrong_password.json()["error"]["message"]

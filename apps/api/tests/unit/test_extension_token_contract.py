from importlib import import_module
from typing import Protocol, cast
from uuid import uuid4

import pytest

from boardtrace_api.auth.tokens import TokenError, TokenScopeError, TokenService
from boardtrace_api.config import Settings


class _Jwt(Protocol):
    def decode(
        self,
        token: str,
        key: str,
        algorithms: list[str],
        *,
        audience: str,
        issuer: str,
    ) -> dict[str, object]: ...


jwt = cast(_Jwt, import_module("jwt"))


def service() -> TokenService:
    return TokenService(
        Settings(
            jwt_signing_secret="test-jwt-signing-secret-with-adequate-length",
            refresh_token_pepper="test-refresh-token-pepper",
        )
    )


def test_extension_claims_use_separate_audience_type_and_scopes() -> None:
    tokens = service()
    token = tokens.issue_extension_token(uuid4(), "boardtrace-test", ("games:ingest",))
    claims = jwt.decode(
        token,
        "test-jwt-signing-secret-with-adequate-length",
        ["HS256"],
        audience="boardtrace-extension",
        issuer="boardtrace-api",
    )
    assert claims["token_type"] == "extension_access"
    assert claims["scopes"] == ["games:ingest"]
    with pytest.raises(TokenScopeError):
        tokens.decode_extension_token(token, "games:read-status")


def test_web_access_token_is_not_an_extension_token() -> None:
    tokens = service()
    with pytest.raises(TokenError):
        tokens.decode_extension_token(tokens.issue_access_token(uuid4()), "games:ingest")


def test_extension_token_rejects_unknown_scope_at_issuance() -> None:
    with pytest.raises(ValueError):
        service().issue_extension_token(uuid4(), "boardtrace-test", ("analysis:read",))

from datetime import UTC, datetime, timedelta
from hmac import digest
from importlib import import_module
from secrets import token_urlsafe
from typing import Protocol, cast
from uuid import UUID, uuid4

from boardtrace_api.config import Settings


class TokenError(Exception):
    pass


class _Jwt(Protocol):
    def encode(self, payload: dict[str, object], key: str, algorithm: str) -> str: ...

    def decode(
        self,
        token: str,
        key: str,
        algorithms: list[str],
        *,
        audience: str,
        issuer: str,
        options: dict[str, list[str]],
    ) -> dict[str, object]: ...


jwt = cast(_Jwt, import_module("jwt"))


class TokenService:
    def __init__(self, settings: Settings) -> None:
        if settings.jwt_signing_secret is None or settings.refresh_token_pepper is None:
            raise ValueError("Authentication secrets must be configured")
        self._settings = settings

    def issue_access_token(self, user_id: UUID) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "iss": self._settings.jwt_issuer,
            "aud": self._settings.jwt_audience,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=self._settings.access_token_lifetime_seconds),
            "jti": str(uuid4()),
            "typ": "access",
        }
        assert self._settings.jwt_signing_secret is not None
        return jwt.encode(payload, self._settings.jwt_signing_secret, self._settings.jwt_algorithm)

    def decode_access_token(self, token: str) -> UUID:
        try:
            assert self._settings.jwt_signing_secret is not None
            claims = jwt.decode(
                token,
                self._settings.jwt_signing_secret,
                [self._settings.jwt_algorithm],
                audience=self._settings.jwt_audience,
                issuer=self._settings.jwt_issuer,
                options={"require": ["sub", "iss", "aud", "iat", "nbf", "exp", "jti", "typ"]},
            )
            if claims["typ"] != "access":
                raise TokenError
            return UUID(str(claims["sub"]))
        except (Exception, ValueError) as error:
            raise TokenError from error

    def new_refresh_token(self) -> str:
        return token_urlsafe(48)

    def digest_refresh_token(self, token: str) -> str:
        assert self._settings.refresh_token_pepper is not None
        return digest(self._settings.refresh_token_pepper.encode(), token.encode(), "sha256").hex()

    def expires_in(self) -> int:
        return self._settings.access_token_lifetime_seconds

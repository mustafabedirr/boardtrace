from datetime import UTC, datetime, timedelta
from hmac import digest
from importlib import import_module
from secrets import token_urlsafe
from typing import Protocol, cast
from uuid import UUID, uuid4

from boardtrace_api.config import Settings


class TokenError(Exception):
    pass


class TokenScopeError(Exception):
    pass


EXTENSION_SCOPES = frozenset({"games:ingest", "games:read-status"})


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
        options: dict[str, object],
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
        return self.decode_user_token(token, "access")

    def issue_extension_token(
        self, user_id: UUID, extension_id: str, scopes: tuple[str, ...]
    ) -> str:
        if not scopes or len(scopes) != len(set(scopes)) or not set(scopes) <= EXTENSION_SCOPES:
            raise ValueError("Extension scopes must be an exact non-empty allowlisted set")
        now = datetime.now(UTC)
        assert self._settings.jwt_signing_secret is not None
        return jwt.encode(
            {
                "sub": str(user_id),
                "iss": self._settings.jwt_issuer,
                "aud": self._settings.extension_jwt_audience,
                "iat": now,
                "nbf": now,
                "exp": now
                + timedelta(seconds=self._settings.extension_access_token_lifetime_seconds),
                "jti": str(uuid4()),
                "token_type": "extension_access",
                "extension_id": extension_id,
                "scopes": list(scopes),
            },
            self._settings.jwt_signing_secret,
            self._settings.jwt_algorithm,
        )

    def decode_extension_token(self, token: str, required_scope: str) -> UUID:
        if required_scope not in EXTENSION_SCOPES:
            raise ValueError("Required extension scope is not allowlisted")
        claims = self._decode(
            token,
            audience=self._settings.extension_jwt_audience,
            required=["sub", "iss", "aud", "iat", "nbf", "exp", "jti", "token_type", "scopes"],
        )
        if claims.get("token_type") != "extension_access":
            raise TokenError
        scopes = claims.get("scopes")
        if (
            not isinstance(scopes, list)
            or not all(isinstance(scope, str) for scope in scopes)
            or len(scopes) != len(set(scopes))
            or not set(scopes) <= EXTENSION_SCOPES
        ):
            raise TokenError
        if required_scope not in scopes:
            raise TokenScopeError
        try:
            return UUID(str(claims["sub"]))
        except (KeyError, ValueError) as error:
            raise TokenError from error

    def decode_user_token(self, token: str, expected_type: str) -> UUID:
        claims = self._decode(
            token,
            audience=self._settings.jwt_audience,
            required=["sub", "iss", "aud", "iat", "nbf", "exp", "jti", "typ"],
        )
        if claims.get("typ") != expected_type:
            raise TokenError
        try:
            return UUID(str(claims["sub"]))
        except (KeyError, ValueError) as error:
            raise TokenError from error

    def _decode(self, token: str, *, audience: str, required: list[str]) -> dict[str, object]:
        try:
            assert self._settings.jwt_signing_secret is not None
            return jwt.decode(
                token,
                self._settings.jwt_signing_secret,
                [self._settings.jwt_algorithm],
                audience=audience,
                issuer=self._settings.jwt_issuer,
                options={"require": required},
            )
        except Exception as error:
            raise TokenError from error

    def new_refresh_token(self) -> str:
        return token_urlsafe(48)

    def digest_refresh_token(self, token: str) -> str:
        assert self._settings.refresh_token_pepper is not None
        return digest(self._settings.refresh_token_pepper.encode(), token.encode(), "sha256").hex()

    def expires_in(self) -> int:
        return self._settings.access_token_lifetime_seconds

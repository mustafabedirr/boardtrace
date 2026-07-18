from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.config import Settings
from boardtrace_api.models import ExtensionPairing


class PairingError(Exception):
    pass


class PairingService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._tokens = TokenService(settings)

    async def create(
        self, user_id: UUID, extension_id: str, scopes: tuple[str, ...]
    ) -> tuple[str, datetime]:
        code = token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(
            seconds=self._settings.extension_pairing_lifetime_seconds
        )
        self._session.add(
            ExtensionPairing(
                code_digest=self._tokens.digest_refresh_token(code),
                user_id=user_id,
                extension_id=extension_id,
                scopes=list(scopes),
                expires_at=expires_at,
            )
        )
        return code, expires_at

    async def exchange(self, code: str, extension_id: str) -> str:
        pairing = await self._session.scalar(
            select(ExtensionPairing)
            .where(ExtensionPairing.code_digest == self._tokens.digest_refresh_token(code))
            .with_for_update()
        )
        if (
            pairing is None
            or pairing.redeemed_at is not None
            or pairing.expires_at <= datetime.now(UTC)
            or pairing.extension_id != extension_id
        ):
            raise PairingError
        pairing.redeemed_at = datetime.now(UTC)
        return self._tokens.issue_extension_token(
            pairing.user_id, extension_id, tuple(pairing.scopes)
        )

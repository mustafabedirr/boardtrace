from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import AuthSession


class AuthSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, auth_session: AuthSession) -> None:
        self._session.add(auth_session)

    async def get_by_token_digest(self, token_digest: str) -> AuthSession | None:
        result = await self._session.execute(
            select(AuthSession).where(AuthSession.token_digest == token_digest)
        )
        return result.scalar_one_or_none()

    async def get_for_update_by_token_digest(self, token_digest: str) -> AuthSession | None:
        result = await self._session.execute(
            select(AuthSession).where(AuthSession.token_digest == token_digest).with_for_update()
        )
        return result.scalar_one_or_none()

    async def revoke(self, auth_session: AuthSession, *, revoked_at: datetime) -> None:
        auth_session.revoked_at = revoked_at

    async def revoke_family(self, family_id: UUID, *, revoked_at: datetime) -> None:
        await self._session.execute(
            update(AuthSession)
            .where(AuthSession.family_id == family_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )

    async def link_replacement(self, auth_session: AuthSession, replacement_id: UUID) -> None:
        auth_session.replaced_by_session_id = replacement_id

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        await self._session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

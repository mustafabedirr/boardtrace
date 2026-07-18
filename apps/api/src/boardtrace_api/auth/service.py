from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.auth.passwords import PasswordService
from boardtrace_api.auth.tokens import TokenService
from boardtrace_api.models import AuthSession, User
from boardtrace_api.schemas.auth import TokenPairResponse


class AuthenticationError(Exception):
    pass


class AuthenticationService:
    def __init__(
        self, session: AsyncSession, passwords: PasswordService, tokens: TokenService
    ) -> None:
        self._session, self._passwords, self._tokens = session, passwords, tokens

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().casefold()

    async def register(
        self, email: str, password: str, display_name: str | None
    ) -> tuple[User, TokenPairResponse]:
        normalized = self.normalize_email(email)
        existing = await self._session.scalar(
            select(User).where(User.normalized_email == normalized)
        )
        if existing is not None:
            raise AuthenticationError
        user = User(
            email=email.strip(),
            normalized_email=normalized,
            display_name=display_name,
            password_hash=self._passwords.hash(password),
        )
        self._session.add(user)
        await self._session.flush()
        return user, await self.issue_pair(user)

    async def login(self, email: str, password: str) -> TokenPairResponse:
        user = await self._session.scalar(
            select(User).where(User.normalized_email == self.normalize_email(email))
        )
        if user is None or user.password_hash is None:
            self._passwords.dummy_verify(password)
            raise AuthenticationError
        if not user.is_active or not self._passwords.verify(password, user.password_hash):
            raise AuthenticationError
        user.last_login_at = datetime.now(UTC)
        return await self.issue_pair(user)

    async def issue_pair(self, user: User, family_id: UUID | None = None) -> TokenPairResponse:
        raw = self._tokens.new_refresh_token()
        self._session.add(
            AuthSession(
                user_id=user.id,
                token_digest=self._tokens.digest_refresh_token(raw),
                family_id=family_id or uuid4(),
                expires_at=datetime.now(UTC)
                + timedelta(seconds=self._tokens._settings.refresh_token_lifetime_seconds),
            )
        )
        return TokenPairResponse(
            access_token=self._tokens.issue_access_token(user.id),
            refresh_token=raw,
            expires_in=self._tokens.expires_in(),
        )

    async def refresh(self, raw: str) -> TokenPairResponse:
        item = await self._session.scalar(
            select(AuthSession)
            .where(AuthSession.token_digest == self._tokens.digest_refresh_token(raw))
            .with_for_update()
        )
        if item is None or item.expires_at <= datetime.now(UTC):
            raise AuthenticationError
        if item.revoked_at is not None:
            await self._session.execute(
                select(AuthSession).where(AuthSession.family_id == item.family_id).with_for_update()
            )
            for session in (
                await self._session.scalars(
                    select(AuthSession).where(AuthSession.family_id == item.family_id)
                )
            ).all():
                session.revoked_at = datetime.now(UTC)
            raise AuthenticationError
        user = await self._session.get(User, item.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError
        item.revoked_at = datetime.now(UTC)
        pair = await self.issue_pair(user, item.family_id)
        await self._session.flush()
        replacement = await self._session.scalar(
            select(AuthSession).where(
                AuthSession.token_digest == self._tokens.digest_refresh_token(pair.refresh_token)
            )
        )
        item.replaced_by_session_id = replacement.id if replacement else None
        return pair

    async def revoke(self, raw: str) -> None:
        item = await self._session.scalar(
            select(AuthSession).where(
                AuthSession.token_digest == self._tokens.digest_refresh_token(raw)
            )
        )
        if item is not None and item.revoked_at is None:
            item.revoked_at = datetime.now(UTC)

    async def revoke_all(self, user_id: UUID) -> None:
        for item in (
            await self._session.scalars(
                select(AuthSession).where(
                    AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
                )
            )
        ).all():
            item.revoked_at = datetime.now(UTC)

    async def current_user(self, token: str) -> User:
        user = await self._session.get(User, self._tokens.decode_access_token(token))
        if user is None or not user.is_active:
            raise AuthenticationError
        return user

    async def extension_user(self, token: str, required_scope: str) -> User:
        user = await self._session.get(
            User, self._tokens.decode_extension_token(token, required_scope)
        )
        if user is None or not user.is_active:
            raise AuthenticationError
        return user

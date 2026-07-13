from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    def add(self, user: User) -> None:
        self._session.add(user)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def update_last_login(self, user_id: UUID, *, occurred_at: datetime) -> bool:
        user = await self.get_by_id(user_id)
        if user is None:
            return False
        user.last_login_at = occurred_at
        return True

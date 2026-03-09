import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AlreadyExistsException, NotFoundException
from src.models.user import User
from src.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self) -> list[User]:
        result = await self.db.execute(
            select(User).order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, user_id: uuid.UUID) -> User:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("User", str(user_id))
        return user

    async def create(self, payload: UserCreate) -> User:
        user = User(**payload.model_dump())
        self.db.add(user)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise AlreadyExistsException("User", "username or email")
        await self.db.refresh(user)
        return user

    async def update(self, user_id: uuid.UUID, payload: UserUpdate) -> User:
        user = await self.get_by_id(user_id)
        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise AlreadyExistsException("User", "username or email")
        await self.db.refresh(user)
        return user

    async def delete(self, user_id: uuid.UUID) -> None:
        user = await self.get_by_id(user_id)
        await self.db.delete(user)
        await self.db.flush()

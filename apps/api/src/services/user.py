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

    async def get_by_clerk_id(self, clerk_id: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.clerk_id == clerk_id)
        )
        return result.scalar_one_or_none()

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

    async def upsert_by_clerk_id(self, payload: UserCreate) -> User:
        """Create or update a user by clerk_id. Used by webhook handlers."""
        user = await self.get_by_clerk_id(payload.clerk_id)
        if user:
            update_data = payload.model_dump(exclude={"clerk_id"})
            for field, value in update_data.items():
                setattr(user, field, value)
            user.is_active = True
        else:
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

    async def update_by_clerk_id(self, clerk_id: str, payload: UserUpdate) -> User:
        """Update a user by clerk_id. Used by webhook handlers."""
        user = await self.get_by_clerk_id(clerk_id)
        if not user:
            raise NotFoundException("User", clerk_id)
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

    async def soft_delete_by_clerk_id(self, clerk_id: str) -> None:
        """Mark user as inactive by clerk_id. Used by webhook handlers."""
        user = await self.get_by_clerk_id(clerk_id)
        if user:
            user.is_active = False
            await self.db.flush()

    async def delete(self, user_id: uuid.UUID) -> None:
        user = await self.get_by_id(user_id)
        await self.db.delete(user)
        await self.db.flush()

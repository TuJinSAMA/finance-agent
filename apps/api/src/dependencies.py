from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.user import UserService

DBSession = Annotated[AsyncSession, Depends(get_db)]


def get_user_service(db: DBSession) -> UserService:
    return UserService(db)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]

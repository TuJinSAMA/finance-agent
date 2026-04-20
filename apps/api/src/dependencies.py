from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import get_current_user
from src.core.database import get_db
from src.core.redis import redis_manager
from src.models.user import User
from src.services.portfolio import PortfolioService
from src.services.user import UserService

DBSession = Annotated[AsyncSession, Depends(get_db)]

CurrentUser = Annotated[User, Depends(get_current_user)]


def get_user_service(db: DBSession) -> UserService:
    return UserService(db)


def get_portfolio_service(db: DBSession) -> PortfolioService:
    return PortfolioService(db)


def get_redis() -> Redis:
    return redis_manager.redis


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
PortfolioServiceDep = Annotated[PortfolioService, Depends(get_portfolio_service)]
RedisDep = Annotated[Redis, Depends(get_redis)]

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import get_current_user
from src.core.database import get_db
from src.core.redis import redis_manager
from src.models.user import User
from src.services.chat_agent import ChatAgentService
from src.services.chat_session import ChatSessionService
from src.services.market_metric_store import MarketMetricService
from src.services.portfolio import PortfolioService
from src.services.geo_news import GeoNewsService
from src.services.user import UserService

DBSession = Annotated[AsyncSession, Depends(get_db)]

CurrentUser = Annotated[User, Depends(get_current_user)]


def get_user_service(db: DBSession) -> UserService:
    return UserService(db)


def get_portfolio_service(db: DBSession) -> PortfolioService:
    return PortfolioService(db)


def get_market_metric_service(db: DBSession) -> MarketMetricService:
    return MarketMetricService(db)


def get_chat_session_service(db: DBSession) -> ChatSessionService:
    return ChatSessionService(db)


def get_chat_agent_service(db: DBSession) -> ChatAgentService:
    return ChatAgentService(db)


def get_geo_news_service(db: DBSession) -> GeoNewsService:
    return GeoNewsService(db)


def get_redis() -> Redis:
    return redis_manager.redis


GeoNewsServiceDep = Annotated[GeoNewsService, Depends(get_geo_news_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
PortfolioServiceDep = Annotated[PortfolioService, Depends(get_portfolio_service)]
MarketMetricServiceDep = Annotated[MarketMetricService, Depends(get_market_metric_service)]
ChatSessionServiceDep = Annotated[ChatSessionService, Depends(get_chat_session_service)]
ChatAgentServiceDep = Annotated[ChatAgentService, Depends(get_chat_agent_service)]
RedisDep = Annotated[Redis, Depends(get_redis)]

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.agents.data_agent.trading_calendar import trading_calendar
from src.core.config import settings
from src.core.database import async_session, engine
from src.core.middleware import RequestLoggingMiddleware
from src.core.scheduler import (
    register_data_agent_jobs,
    register_default_jobs,
    register_event_agent_jobs,
    register_orchestrator_jobs,
    register_recommendation_jobs,
    scheduler,
)
from src.routers import admin, notifications, portfolio, recommendations, users, webhooks

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log = logging.getLogger(__name__)
    try:
        await trading_calendar.load()
    except Exception:
        log.warning("Failed to load trading calendar — jobs will treat every day as non-trading")

    register_default_jobs()
    register_data_agent_jobs()
    register_orchestrator_jobs()
    register_event_agent_jobs()
    register_recommendation_jobs()
    scheduler.start()
    log.info("APScheduler started")
    yield
    scheduler.shutdown(wait=False)
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(recommendations.router, prefix=settings.API_V1_PREFIX)
app.include_router(portfolio.router, prefix=settings.API_V1_PREFIX)
app.include_router(notifications.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router, prefix=settings.API_V1_PREFIX)
app.include_router(webhooks.router, prefix="/api")


@app.get("/health")
async def health_check():
    async with async_session() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}

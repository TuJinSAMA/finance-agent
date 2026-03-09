from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from src.database import async_session, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Finance Agent API", lifespan=lifespan)


@app.get("/health")
async def health_check():
    async with async_session() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}

import logging

from redis.asyncio import ConnectionPool, Redis

logger = logging.getLogger(__name__)


class RedisManager:
    """Manage Redis connection pool lifecycle bound to FastAPI app lifespan."""

    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None

    async def init(self, url: str, *, max_connections: int = 10) -> None:
        self._pool = ConnectionPool.from_url(
            url,
            max_connections=max_connections,
            decode_responses=True,
        )
        self._redis = Redis(connection_pool=self._pool)
        await self._redis.ping()
        logger.info("Redis connected: %s", url.split("@")[-1])

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None
            logger.info("Redis connection pool closed")

    @property
    def redis(self) -> Redis:
        if self._redis is None:
            raise RuntimeError("RedisManager has not been initialized. Call init() first.")
        return self._redis


redis_manager = RedisManager()
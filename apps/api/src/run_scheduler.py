import asyncio
import logging
from threading import Event

from redis.asyncio import Redis

from src.core.config import settings
from src.core.scheduler import register_geo_news_jobs
from src.core.scheduler import register_public_market_jobs
from src.core.scheduler import refresh_crypto_snapshot
from src.core.scheduler import refresh_equity_snapshot
from src.core.scheduler import refresh_extended_snapshot
from src.core.scheduler import scheduler


logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def _run_startup_refreshes() -> None:
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await refresh_crypto_snapshot(redis)
        await refresh_extended_snapshot(redis)
        await refresh_equity_snapshot(redis)
    finally:
        await redis.aclose()


def main() -> None:
    stop_event = Event()

    try:
        logger.info("Initializing standalone scheduler")
        asyncio.run(_run_startup_refreshes())
        register_public_market_jobs()
        register_geo_news_jobs()
        scheduler.start()
        logger.info("Standalone scheduler started")

        stop_event.wait()
    except KeyboardInterrupt:
        logger.info("Scheduler shutdown requested")
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
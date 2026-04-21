import asyncio
import logging
from threading import Event

from src.core.config import settings
from src.core.scheduler import close_scheduler_redis
from src.core.scheduler import register_public_market_jobs
from src.core.scheduler import refresh_market_assets_snapshot
from src.core.scheduler import refresh_market_macro_snapshot
from src.core.scheduler import scheduler


logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def _run_startup_refreshes() -> None:
    await refresh_market_macro_snapshot()
    await refresh_market_assets_snapshot()


def main() -> None:
    stop_event = Event()

    try:
        logger.info("Initializing standalone scheduler")
        asyncio.run(_run_startup_refreshes())
        register_public_market_jobs()
        scheduler.start()
        logger.info("Standalone scheduler started")

        stop_event.wait()
    except KeyboardInterrupt:
        logger.info("Scheduler shutdown requested")
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        asyncio.run(close_scheduler_redis())


if __name__ == "__main__":
    main()

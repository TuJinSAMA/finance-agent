from datetime import datetime, timedelta

from redis.asyncio import Redis

from src.schemas.public_board import GroupStatus
from src.schemas.public_board import MarketGroupSnapshot
from src.schemas.public_board import SnapshotGroup


CACHE_VERSION = "v1"
SNAPSHOT_TTL_SECONDS = 45 * 60
FRESH_WINDOW = timedelta(minutes=15)
STALE_WINDOW = timedelta(minutes=45)


def snapshot_cache_key(group: SnapshotGroup) -> str:
    return f"public:market:{group}:{CACHE_VERSION}"


def classify_snapshot_status(
    snapshot: MarketGroupSnapshot,
    now: datetime,
) -> GroupStatus:
    age = now - snapshot.as_of
    if age <= FRESH_WINDOW:
        return "ok"
    if age <= STALE_WINDOW:
        return "stale"
    return "empty"


async def write_market_snapshot(
    redis: Redis,
    snapshot: MarketGroupSnapshot,
) -> None:
    await redis.set(
        snapshot_cache_key(snapshot.group),
        snapshot.model_dump_json(),
        ex=SNAPSHOT_TTL_SECONDS,
    )


async def read_market_snapshot(
    redis: Redis,
    group: SnapshotGroup,
) -> MarketGroupSnapshot | None:
    raw = await redis.get(snapshot_cache_key(group))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return MarketGroupSnapshot.model_validate_json(raw)

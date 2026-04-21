from datetime import datetime, timedelta

from redis.asyncio import Redis

from src.schemas.public_board import GroupStatus
from src.schemas.public_board import MarketGroupSnapshot
from src.schemas.public_board import SnapshotGroup


CACHE_VERSION = "v1"

_GROUP_TTL_SECONDS: dict[str, int] = {
    "crypto": 30 * 60,
    "extended": 60 * 60,
    "equity": 60 * 60,
    "macro": 45 * 60,
    "assets": 45 * 60,
}

_GROUP_FRESH_WINDOW: dict[str, timedelta] = {
    "crypto": timedelta(minutes=5),
    "extended": timedelta(minutes=15),
    "equity": timedelta(minutes=15),
    "macro": timedelta(minutes=15),
    "assets": timedelta(minutes=15),
}

_GROUP_STALE_WINDOW: dict[str, timedelta] = {
    "crypto": timedelta(minutes=30),
    "extended": timedelta(minutes=60),
    "equity": timedelta(minutes=60),
    "macro": timedelta(minutes=45),
    "assets": timedelta(minutes=45),
}


def snapshot_cache_key(group: SnapshotGroup) -> str:
    return f"public:market:{group}:{CACHE_VERSION}"


def classify_snapshot_status(
    snapshot: MarketGroupSnapshot,
    now: datetime,
) -> GroupStatus:
    fresh_window = _GROUP_FRESH_WINDOW.get(snapshot.group, timedelta(minutes=15))
    stale_window = _GROUP_STALE_WINDOW.get(snapshot.group, timedelta(minutes=45))
    age = now - snapshot.as_of
    if age <= fresh_window:
        return "ok"
    if age <= stale_window:
        return "stale"
    return "empty"


async def write_market_snapshot(
    redis: Redis,
    snapshot: MarketGroupSnapshot,
) -> None:
    ttl = _GROUP_TTL_SECONDS.get(snapshot.group, 45 * 60)
    await redis.set(
        snapshot_cache_key(snapshot.group),
        snapshot.model_dump_json(),
        ex=ttl,
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
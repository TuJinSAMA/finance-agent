import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schemas.public_board import MarketGroupSnapshot
from src.schemas.public_board import MarketMetric
from src.services import public_market_cache
from src.core import scheduler as scheduler_module
from src.services.public_market_cache import classify_snapshot_status
from src.services.public_market_cache import read_market_snapshot
from src.services.public_market_cache import snapshot_cache_key
from src.services.public_market_cache import write_market_snapshot


class FakeRedis:
    def __init__(self, value: str | bytes | None = None) -> None:
        self.value = value
        self.last_key: str | None = None
        self.last_payload: str | None = None
        self.last_ttl: int | None = None
        self.closed = False
        self.pinged = False

    async def get(self, key: str) -> str | bytes | None:
        self.last_key = key
        return self.value

    async def ping(self) -> None:
        self.pinged = True

    async def set(self, key: str, value: str, ex: int) -> None:
        self.last_key = key
        self.last_payload = value
        self.last_ttl = ex
        self.value = value

    async def aclose(self) -> None:
        self.closed = True


def build_snapshot(*, as_of: datetime) -> MarketGroupSnapshot:
    return MarketGroupSnapshot(
        group="macro",
        status="ok",
        as_of=as_of,
        last_success_at=as_of,
        source="akshare",
        items=[
            MarketMetric(
                name="VIX",
                symbol="^VIX",
                value=18.0,
                display="18.0",
                change_pct=0.0,
                status="ok",
            )
        ],
    )


def test_snapshot_cache_key_uses_group_and_version() -> None:
    assert snapshot_cache_key("macro") == "public:market:macro:v1"
    assert snapshot_cache_key("assets") == "public:market:assets:v1"


def test_classify_snapshot_status_marks_fresh_snapshot_ok() -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)

    status = classify_snapshot_status(
        build_snapshot(as_of=now - timedelta(minutes=15)),
        now,
    )

    assert status == "ok"


def test_classify_snapshot_status_marks_old_data_stale() -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)

    status = classify_snapshot_status(
        build_snapshot(as_of=now - timedelta(minutes=20)),
        now,
    )

    assert status == "stale"


def test_classify_snapshot_status_marks_exact_45_minutes_stale() -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)

    status = classify_snapshot_status(
        build_snapshot(as_of=now - timedelta(minutes=45)),
        now,
    )

    assert status == "stale"


def test_classify_snapshot_status_marks_expired_snapshot_empty() -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)

    status = classify_snapshot_status(
        build_snapshot(as_of=now - timedelta(minutes=46)),
        now,
    )

    assert status == "empty"


def test_write_market_snapshot_stores_json_with_ttl() -> None:
    snapshot = build_snapshot(as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC))
    redis = FakeRedis()

    import asyncio

    asyncio.run(write_market_snapshot(redis, snapshot))

    assert redis.last_key == "public:market:macro:v1"
    assert redis.last_payload is not None
    assert MarketGroupSnapshot.model_validate_json(redis.last_payload) == snapshot
    assert redis.last_ttl == 45 * 60


def test_refresh_market_macro_snapshot_writes_cache_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = build_snapshot(as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC))
    redis = FakeRedis()

    async def fake_build_macro_snapshot(as_of: datetime) -> MarketGroupSnapshot:
        return snapshot.model_copy(update={"as_of": as_of, "last_success_at": as_of})

    monkeypatch.setattr(
        scheduler_module,
        "build_macro_snapshot",
        fake_build_macro_snapshot,
    )

    import asyncio

    asyncio.run(scheduler_module.refresh_market_macro_snapshot(redis))

    assert redis.last_key == public_market_cache.snapshot_cache_key("macro")
    assert redis.last_payload is not None
    written_snapshot = MarketGroupSnapshot.model_validate_json(redis.last_payload)
    assert written_snapshot.group == "macro"
    assert redis.last_ttl == 45 * 60


def test_refresh_market_macro_snapshot_closes_internal_redis_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = build_snapshot(as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC))
    redis = FakeRedis()

    async def fake_build_macro_snapshot(as_of: datetime) -> MarketGroupSnapshot:
        return snapshot.model_copy(update={"as_of": as_of, "last_success_at": as_of})

    monkeypatch.setattr(
        scheduler_module,
        "build_macro_snapshot",
        fake_build_macro_snapshot,
    )
    monkeypatch.setattr(
        scheduler_module.Redis,
        "from_url",
        lambda *args, **kwargs: redis,
    )

    import asyncio

    asyncio.run(scheduler_module.refresh_market_macro_snapshot())

    assert redis.pinged is True
    assert redis.closed is True
    assert redis.last_key == public_market_cache.snapshot_cache_key("macro")
    assert redis.last_ttl == 45 * 60


def test_register_public_market_jobs_replaces_existing_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeScheduler:
        def add_job(self, func, trigger, **kwargs) -> None:
            calls.append(
                {
                    "func": func,
                    "trigger": trigger,
                    **kwargs,
                }
            )

    monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())

    scheduler_module.register_public_market_jobs()
    scheduler_module.register_public_market_jobs()

    assert len(calls) == 4
    assert [call["id"] for call in calls] == [
        "refresh_public_market_macro",
        "refresh_public_market_assets",
        "refresh_public_market_macro",
        "refresh_public_market_assets",
    ]
    assert all(call["trigger"] == "interval" for call in calls)
    assert all(call["minutes"] == 15 for call in calls)
    assert all(call["replace_existing"] is True for call in calls)


def test_read_market_snapshot_decodes_bytes_and_validates_json() -> None:
    snapshot = build_snapshot(as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC))
    redis = FakeRedis(snapshot.model_dump_json().encode("utf-8"))

    import asyncio

    result = asyncio.run(read_market_snapshot(redis, "macro"))

    assert result == snapshot
    assert redis.last_key == "public:market:macro:v1"


def test_read_market_snapshot_returns_none_when_missing() -> None:
    redis = FakeRedis()

    import asyncio

    result = asyncio.run(read_market_snapshot(redis, "macro"))

    assert result is None


def test_read_market_snapshot_raises_for_invalid_payload() -> None:
    redis = FakeRedis("{\"group\":\"macro\"}")

    import asyncio

    with pytest.raises(ValidationError):
        asyncio.run(read_market_snapshot(redis, "macro"))

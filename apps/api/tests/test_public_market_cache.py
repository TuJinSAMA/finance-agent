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


def build_snapshot(*, group: str = "macro", as_of: datetime) -> MarketGroupSnapshot:
    return MarketGroupSnapshot(
        group=group,
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
    assert snapshot_cache_key("crypto") == "public:market:crypto:v1"
    assert snapshot_cache_key("extended") == "public:market:extended:v1"
    assert snapshot_cache_key("equity") == "public:market:equity:v1"


def test_classify_snapshot_status_marks_fresh_snapshot_ok() -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    for group, fresh_minutes in [("macro", 15), ("assets", 15), ("crypto", 5), ("extended", 15), ("equity", 15)]:
        status = classify_snapshot_status(
            build_snapshot(group=group, as_of=now - timedelta(minutes=fresh_minutes)),
            now,
        )
        assert status == "ok", f"{group}: expected ok, got {status}"


def test_classify_snapshot_status_marks_old_data_stale() -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    for group, fresh_minutes in [("macro", 16), ("assets", 16), ("crypto", 6), ("extended", 16), ("equity", 16)]:
        status = classify_snapshot_status(
            build_snapshot(group=group, as_of=now - timedelta(minutes=fresh_minutes)),
            now,
        )
        assert status == "stale", f"{group}: expected stale, got {status}"


def test_classify_snapshot_status_crypto_stale_boundary() -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    status = classify_snapshot_status(
        build_snapshot(group="crypto", as_of=now - timedelta(minutes=30)),
        now,
    )
    assert status == "stale"


def test_classify_snapshot_status_extended_stale_boundary() -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    status = classify_snapshot_status(
        build_snapshot(group="extended", as_of=now - timedelta(minutes=60)),
        now,
    )
    assert status == "stale"


def test_classify_snapshot_status_equity_stale_boundary() -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    status = classify_snapshot_status(
        build_snapshot(group="equity", as_of=now - timedelta(minutes=60)),
        now,
    )
    assert status == "stale"


def test_classify_snapshot_status_marks_expired_snapshot_empty() -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    for group, stale_minutes in [("macro", 46), ("assets", 46), ("crypto", 31), ("extended", 61), ("equity", 61)]:
        status = classify_snapshot_status(
            build_snapshot(group=group, as_of=now - timedelta(minutes=stale_minutes)),
            now,
        )
        assert status == "empty", f"{group}: expected empty, got {status}"


def test_write_market_snapshot_uses_per_group_ttl() -> None:
    import asyncio

    for group, expected_ttl in [("crypto", 30 * 60), ("extended", 60 * 60), ("equity", 60 * 60)]:
        snapshot = build_snapshot(group=group, as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC))
        redis = FakeRedis()
        asyncio.run(write_market_snapshot(redis, snapshot))

        assert redis.last_key == f"public:market:{group}:v1"
        assert redis.last_ttl == expected_ttl, f"{group}: expected TTL {expected_ttl}, got {redis.last_ttl}"


def test_write_market_snapshot_stores_json_with_ttl() -> None:
    snapshot = build_snapshot(group="macro", as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC))
    redis = FakeRedis()

    import asyncio

    asyncio.run(write_market_snapshot(redis, snapshot))

    assert redis.last_key == "public:market:macro:v1"
    assert redis.last_payload is not None
    assert MarketGroupSnapshot.model_validate_json(redis.last_payload) == snapshot
    assert redis.last_ttl == 45 * 60


def test_refresh_crypto_snapshot_writes_cache_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = build_snapshot(group="crypto", as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC))
    redis = FakeRedis()

    async def fake_build_crypto_snapshot(as_of: datetime) -> MarketGroupSnapshot:
        return snapshot.model_copy(update={"as_of": as_of, "last_success_at": as_of})

    monkeypatch.setattr(
        scheduler_module,
        "build_crypto_snapshot",
        fake_build_crypto_snapshot,
    )

    import asyncio

    asyncio.run(scheduler_module.refresh_crypto_snapshot(redis))

    assert redis.last_key == public_market_cache.snapshot_cache_key("crypto")
    assert redis.last_ttl == 30 * 60


def test_get_scheduler_redis_reuses_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()

    monkeypatch.setattr(
        scheduler_module.Redis,
        "from_url",
        lambda *args, **kwargs: redis,
    )
    monkeypatch.setattr(scheduler_module, "_scheduler_redis", None, raising=False)

    import asyncio

    result1 = asyncio.run(scheduler_module.get_scheduler_redis())
    result2 = asyncio.run(scheduler_module.get_scheduler_redis())

    assert result1 is result2
    assert redis.pinged is True
    assert redis.closed is False

    asyncio.run(scheduler_module.close_scheduler_redis())
    assert redis.closed is True


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

        def reschedule_job(self, job_id, **kwargs) -> None:
            pass

    monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())

    scheduler_module.register_public_market_jobs()
    scheduler_module.register_public_market_jobs()

    assert len(calls) == 6
    job_ids = [call["id"] for call in calls]
    assert job_ids == [
        "refresh_crypto", "refresh_extended", "refresh_equity",
        "refresh_crypto", "refresh_extended", "refresh_equity",
    ]
    assert all(call["trigger"] == "interval" for call in calls)
    assert all(call["replace_existing"] is True for call in calls)
    assert calls[0]["minutes"] == 5
    assert calls[1]["minutes"] == 10
    assert calls[2]["minutes"] == 15


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


class TestCurrentSession:
    def test_weekend_saturday(self, monkeypatch: pytest.MonkeyPatch) -> None:
        saturday = datetime(2026, 4, 18, 12, 0, tzinfo=scheduler_module.ET)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: saturday)
        assert scheduler_module._current_session() == "weekend"

    def test_weekend_sunday(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sunday = datetime(2026, 4, 19, 15, 0, tzinfo=scheduler_module.ET)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: sunday)
        assert scheduler_module._current_session() == "weekend"

    def test_us_regular_10am(self, monkeypatch: pytest.MonkeyPatch) -> None:
        weekday_10am = datetime(2026, 4, 20, 10, 0, tzinfo=scheduler_module.ET)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: weekday_10am)
        assert scheduler_module._current_session() == "us_regular"

    def test_us_regular_market_close_boundary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        weekday_330pm = datetime(2026, 4, 20, 15, 59, tzinfo=scheduler_module.ET)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: weekday_330pm)
        assert scheduler_module._current_session() == "us_regular"

    def test_us_extended_premarket_7am(self, monkeypatch: pytest.MonkeyPatch) -> None:
        weekday_7am = datetime(2026, 4, 20, 7, 0, tzinfo=scheduler_module.ET)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: weekday_7am)
        assert scheduler_module._current_session() == "us_extended"

    def test_us_extended_afterhours_5pm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        weekday_5pm = datetime(2026, 4, 20, 17, 0, tzinfo=scheduler_module.ET)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: weekday_5pm)
        assert scheduler_module._current_session() == "us_extended"

    def test_us_extended_4am(self, monkeypatch: pytest.MonkeyPatch) -> None:
        weekday_4am = datetime(2026, 4, 20, 4, 0, tzinfo=scheduler_module.ET)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: weekday_4am)
        assert scheduler_module._current_session() == "us_extended"

    def test_overnight_2am(self, monkeypatch: pytest.MonkeyPatch) -> None:
        weekday_2am = datetime(2026, 4, 20, 2, 0, tzinfo=scheduler_module.ET)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: weekday_2am)
        assert scheduler_module._current_session() == "overnight"

    def test_overnight_10pm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        weekday_10pm = datetime(2026, 4, 20, 22, 0, tzinfo=scheduler_module.ET)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: weekday_10pm)
        assert scheduler_module._current_session() == "overnight"


class TestSelfAdjustingJob:
    def test_equity_skips_on_weekend(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[str] = []
        reschedule_calls: list[dict[str, object]] = []

        async def fake_refresh_equity(redis=None) -> None:
            calls.append("equity")

        monkeypatch.setattr(scheduler_module, "refresh_equity_snapshot", fake_refresh_equity)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: datetime(2026, 4, 18, 12, 0, tzinfo=scheduler_module.ET))

        class FakeScheduler:
            def reschedule_job(self, job_id, **kwargs) -> None:
                reschedule_calls.append({"job_id": job_id, **kwargs})

        monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())

        job = scheduler_module._make_self_adjusting_job("equity")
        job()

        assert calls == []
        assert reschedule_calls == []

    def test_crypto_reschedules_on_regular_session(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[str] = []
        reschedule_calls: list[dict[str, object]] = []

        async def fake_refresh_crypto(redis=None) -> None:
            calls.append("crypto")

        monkeypatch.setattr(scheduler_module, "refresh_crypto_snapshot", fake_refresh_crypto)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: datetime(2026, 4, 20, 10, 0, tzinfo=scheduler_module.ET))

        class FakeScheduler:
            def reschedule_job(self, job_id, **kwargs) -> None:
                reschedule_calls.append({"job_id": job_id, **kwargs})

        monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())

        job = scheduler_module._make_self_adjusting_job("crypto")
        job()

        assert calls == ["crypto"]
        assert len(reschedule_calls) == 1
        assert reschedule_calls[0]["job_id"] == "refresh_crypto"
        assert reschedule_calls[0]["minutes"] == 2

    def test_extended_reschedules_on_extended_session(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[str] = []
        reschedule_calls: list[dict[str, object]] = []

        async def fake_refresh_extended(redis=None) -> None:
            calls.append("extended")

        monkeypatch.setattr(scheduler_module, "refresh_extended_snapshot", fake_refresh_extended)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: datetime(2026, 4, 20, 7, 0, tzinfo=scheduler_module.ET))

        class FakeScheduler:
            def reschedule_job(self, job_id, **kwargs) -> None:
                reschedule_calls.append({"job_id": job_id, **kwargs})

        monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())

        job = scheduler_module._make_self_adjusting_job("extended")
        job()

        assert calls == ["extended"]
        assert len(reschedule_calls) == 1
        assert reschedule_calls[0]["job_id"] == "refresh_extended"
        assert reschedule_calls[0]["minutes"] == 10

    def test_equity_reschedules_on_regular_session(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[str] = []
        reschedule_calls: list[dict[str, object]] = []

        async def fake_refresh_equity(redis=None) -> None:
            calls.append("equity")

        monkeypatch.setattr(scheduler_module, "refresh_equity_snapshot", fake_refresh_equity)
        monkeypatch.setattr(scheduler_module, "_now_et", lambda: datetime(2026, 4, 20, 10, 0, tzinfo=scheduler_module.ET))

        class FakeScheduler:
            def reschedule_job(self, job_id, **kwargs) -> None:
                reschedule_calls.append({"job_id": job_id, **kwargs})

        monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())

        job = scheduler_module._make_self_adjusting_job("equity")
        job()

        assert calls == ["equity"]
        assert reschedule_calls[0]["minutes"] == 3
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dependencies import get_redis
from src.routers.public import router
from src.schemas.public_board import MarketGroupSnapshot
from src.schemas.public_board import MarketMetric


class FakeRedis:
    def __init__(self, snapshots: dict[str, MarketGroupSnapshot | None]) -> None:
        self.snapshots = snapshots


class FrozenDateTime(datetime):
    current: datetime

    @classmethod
    def now(cls, tz=None) -> datetime:
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


def build_snapshot(
    *,
    group: str,
    as_of: datetime,
    status: str = "ok",
) -> MarketGroupSnapshot:
    return MarketGroupSnapshot(
        group=group,
        status=status,
        as_of=as_of,
        last_success_at=as_of,
        source="akshare",
        items=[
            MarketMetric(
                name="Test Metric",
                symbol="TEST",
                value=123.45,
                display="123.45",
                change_pct=1.23,
                status="ok",
            )
        ],
    )


def create_client(redis: FakeRedis) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_redis] = lambda: redis
    return TestClient(app)


async def fake_read_market_snapshot(
    redis: FakeRedis,
    group: str,
) -> MarketGroupSnapshot | None:
    return redis.snapshots.get(group)


def test_market_macro_cached_snapshot_returns_200(monkeypatch) -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    snapshot = build_snapshot(
        group="macro",
        as_of=datetime(2026, 4, 20, 10, 20, tzinfo=UTC),
        status="empty",
    )
    client = create_client(FakeRedis({"macro": snapshot}))

    monkeypatch.setattr(
        "src.routers.public.read_market_snapshot",
        fake_read_market_snapshot,
    )
    FrozenDateTime.current = now
    monkeypatch.setattr("src.routers.public.datetime", FrozenDateTime)

    response = client.get("/api/v1/public/market-macro")

    assert response.status_code == 200
    assert response.json()["group"] == "macro"
    assert response.json()["status"] == "ok"
    assert response.json()["as_of"] == "2026-04-20T10:20:00Z"


def test_market_assets_missing_snapshot_returns_503(monkeypatch) -> None:
    client = create_client(FakeRedis({"assets": None}))

    monkeypatch.setattr(
        "src.routers.public.read_market_snapshot",
        fake_read_market_snapshot,
    )

    response = client.get("/api/v1/public/market-assets")

    assert response.status_code == 503
    assert response.json()["detail"] == "assets market snapshot unavailable"


def test_market_assets_stale_snapshot_returns_200_with_stale_status(
    monkeypatch,
) -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    snapshot = build_snapshot(
        group="assets",
        as_of=datetime(2026, 4, 20, 10, 10, tzinfo=UTC),
        status="ok",
    )
    client = create_client(FakeRedis({"assets": snapshot}))

    monkeypatch.setattr(
        "src.routers.public.read_market_snapshot",
        fake_read_market_snapshot,
    )
    FrozenDateTime.current = now
    monkeypatch.setattr("src.routers.public.datetime", FrozenDateTime)

    response = client.get("/api/v1/public/market-assets")

    assert response.status_code == 200
    assert response.json()["group"] == "assets"
    assert response.json()["status"] == "stale"


def test_market_board_route_returns_404() -> None:
    client = create_client(FakeRedis({}))

    response = client.get("/api/v1/public/market-board")

    assert response.status_code == 404

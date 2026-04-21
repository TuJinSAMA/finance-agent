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
    items: list[MarketMetric] | None = None,
) -> MarketGroupSnapshot:
    default_items = [
        MarketMetric(
            name="Test Metric",
            symbol="TEST",
            value=123.45,
            display="123.45",
            change_pct=1.23,
            status="ok",
        )
    ]
    return MarketGroupSnapshot(
        group=group,
        status=status,
        as_of=as_of,
        last_success_at=as_of,
        source="akshare",
        items=items or default_items,
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


def test_market_macro_composes_from_extended_cache(monkeypatch) -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    extended_snapshot = build_snapshot(
        group="extended",
        as_of=datetime(2026, 4, 20, 10, 25, tzinfo=UTC),
        status="ok",
        items=[
            MarketMetric(name="VIX", symbol="^VIX", value=18.0, display="18.0", change_pct=0.0, status="ok"),
            MarketMetric(name="US 10Y", symbol="^TNX", value=4.5, display="4.50%", change_pct=0.1, status="ok"),
            MarketMetric(name="DXY", symbol="DX-Y.NYB", value=104.0, display="104.00", change_pct=0.0, status="ok"),
            MarketMetric(name="2Y-10Y Spread", symbol="^UST2Y/^TNX", value=30.0, display="30.0 bps", change_pct=None, status="ok"),
            MarketMetric(name="Gold", symbol="GC=F", value=2360.0, display="2,360.00", change_pct=0.0, status="ok"),
            MarketMetric(name="WTI", symbol="CL=F", value=81.0, display="81.00", change_pct=0.0, status="ok"),
        ],
    )
    client = create_client(FakeRedis({"extended": extended_snapshot}))

    monkeypatch.setattr(
        "src.routers.public.read_market_snapshot",
        fake_read_market_snapshot,
    )
    FrozenDateTime.current = now
    monkeypatch.setattr("src.routers.public.datetime", FrozenDateTime)

    response = client.get("/api/v1/public/market-macro")

    assert response.status_code == 200
    data = response.json()
    assert data["group"] == "macro"
    assert data["status"] == "ok"
    macro_names = [item["name"] for item in data["items"]]
    assert "VIX" in macro_names
    assert "US 10Y" in macro_names
    assert "DXY" in macro_names
    assert "2Y-10Y Spread" in macro_names
    assert "Gold" not in macro_names
    assert "WTI" not in macro_names


def test_market_assets_composes_from_all_groups(monkeypatch) -> None:
    now = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    crypto_snapshot = build_snapshot(
        group="crypto",
        as_of=datetime(2026, 4, 20, 10, 28, tzinfo=UTC),
        items=[
            MarketMetric(name="BTC", symbol="BTC-USD", value=70000.0, display="70,000.00", change_pct=0.72, status="ok"),
        ],
    )
    equity_snapshot = build_snapshot(
        group="equity",
        as_of=datetime(2026, 4, 20, 10, 25, tzinfo=UTC),
        items=[
            MarketMetric(name="S&P 500", symbol="^GSPC", value=5300.0, display="5,300.00", change_pct=0.76, status="ok"),
            MarketMetric(name="NASDAQ", symbol="^IXIC", value=16750.0, display="16,750.00", change_pct=0.9, status="ok"),
        ],
    )
    extended_snapshot = build_snapshot(
        group="extended",
        as_of=datetime(2026, 4, 20, 10, 26, tzinfo=UTC),
        items=[
            MarketMetric(name="VIX", symbol="^VIX", value=18.0, display="18.0", change_pct=0.0, status="ok"),
            MarketMetric(name="Gold", symbol="GC=F", value=2360.0, display="2,360.00", change_pct=0.0, status="ok"),
            MarketMetric(name="WTI", symbol="CL=F", value=81.0, display="81.00", change_pct=0.0, status="ok"),
        ],
    )
    client = create_client(FakeRedis({
        "crypto": crypto_snapshot,
        "equity": equity_snapshot,
        "extended": extended_snapshot,
    }))

    monkeypatch.setattr(
        "src.routers.public.read_market_snapshot",
        fake_read_market_snapshot,
    )
    FrozenDateTime.current = now
    monkeypatch.setattr("src.routers.public.datetime", FrozenDateTime)

    response = client.get("/api/v1/public/market-assets")

    assert response.status_code == 200
    data = response.json()
    assert data["group"] == "assets"
    asset_names = [item["name"] for item in data["items"]]
    assert "Gold" in asset_names
    assert "WTI" in asset_names
    assert "BTC" in asset_names
    assert "S&P 500" in asset_names
    assert "NASDAQ" in asset_names


def test_market_assets_missing_all_snapshots_returns_503(monkeypatch) -> None:
    client = create_client(FakeRedis({"crypto": None, "equity": None, "extended": None}))

    monkeypatch.setattr(
        "src.routers.public.read_market_snapshot",
        fake_read_market_snapshot,
    )

    response = client.get("/api/v1/public/market-assets")

    assert response.status_code == 503
    assert response.json()["detail"] == "assets market snapshot unavailable"


def test_market_macro_missing_snapshot_returns_503(monkeypatch) -> None:
    client = create_client(FakeRedis({"extended": None}))

    monkeypatch.setattr(
        "src.routers.public.read_market_snapshot",
        fake_read_market_snapshot,
    )

    response = client.get("/api/v1/public/market-macro")

    assert response.status_code == 503
    assert response.json()["detail"] == "macro market snapshot unavailable"


def test_market_board_route_returns_404() -> None:
    client = create_client(FakeRedis({}))

    response = client.get("/api/v1/public/market-board")

    assert response.status_code == 404
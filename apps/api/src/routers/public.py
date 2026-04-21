import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from src.dependencies import RedisDep
from src.schemas.public_board import MarketGroupSnapshot
from src.schemas.public_board import MarketMetric
from src.services.public_board import ASSET_ITEM_NAMES_FROM_EXTENDED
from src.services.public_board import SOURCE_NAME
from src.services.public_market_cache import classify_snapshot_status
from src.services.public_market_cache import read_market_snapshot

router = APIRouter(prefix="/public", tags=["public"])

MACRO_ITEM_NAMES = {"VIX", "US 10Y", "DXY", "2Y-10Y Spread"}


async def _compose_macro_snapshot(redis: RedisDep) -> MarketGroupSnapshot:
    extended = await read_market_snapshot(redis, "extended")
    if extended is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="macro market snapshot unavailable",
        )

    extended_status = classify_snapshot_status(extended, datetime.now(UTC))
    if extended_status == "empty":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="macro market snapshot unavailable",
        )

    macro_items = [item for item in extended.items if item.name in MACRO_ITEM_NAMES]
    return MarketGroupSnapshot(
        group="macro",
        status=extended_status,
        as_of=extended.as_of,
        last_success_at=extended.last_success_at,
        source=extended.source,
        items=macro_items,
    )


async def _compose_assets_snapshot(redis: RedisDep) -> MarketGroupSnapshot:
    crypto, equity, extended = await asyncio.gather(
        read_market_snapshot(redis, "crypto"),
        read_market_snapshot(redis, "equity"),
        read_market_snapshot(redis, "extended"),
    )

    snapshots = {
        "crypto": crypto,
        "equity": equity,
        "extended": extended,
    }

    available = {k: v for k, v in snapshots.items() if v is not None}

    if not available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="assets market snapshot unavailable",
        )

    now = datetime.now(UTC)
    asset_items: list[MarketMetric] = []

    if extended is not None:
        asset_items.extend(
            item for item in extended.items
            if item.name in ASSET_ITEM_NAMES_FROM_EXTENDED
        )

    if crypto is not None:
        asset_items.extend(crypto.items)

    if equity is not None:
        asset_items.extend(equity.items)

    overall_status = "ok"
    latest_as_of = max(s.as_of for s in available.values())
    latest_success = max(s.last_success_at for s in available.values())

    for group_name, snapshot in available.items():
        s = classify_snapshot_status(snapshot, now)
        if s == "empty":
            overall_status = "stale"
        elif s == "stale" and overall_status != "stale":
            overall_status = "stale"

    return MarketGroupSnapshot(
        group="assets",
        status=overall_status,
        as_of=latest_as_of,
        last_success_at=latest_success,
        source=SOURCE_NAME,
        items=asset_items,
    )


@router.get("/market-macro", response_model=MarketGroupSnapshot)
async def get_market_macro(redis: RedisDep) -> MarketGroupSnapshot:
    return await _compose_macro_snapshot(redis)


@router.get("/market-assets", response_model=MarketGroupSnapshot)
async def get_market_assets(redis: RedisDep) -> MarketGroupSnapshot:
    return await _compose_assets_snapshot(redis)
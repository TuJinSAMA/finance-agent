from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from src.dependencies import RedisDep
from src.schemas.public_board import MarketGroupSnapshot
from src.schemas.public_board import SnapshotGroup
from src.services.public_market_cache import classify_snapshot_status
from src.services.public_market_cache import read_market_snapshot

router = APIRouter(prefix="/public", tags=["public"])


async def _get_market_snapshot_or_503(
    redis: RedisDep,
    group: SnapshotGroup,
) -> MarketGroupSnapshot:
    snapshot = await read_market_snapshot(redis, group)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{group} market snapshot unavailable",
        )

    snapshot_status = classify_snapshot_status(snapshot, datetime.now(UTC))
    if snapshot_status == "empty":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{group} market snapshot unavailable",
        )

    return snapshot.model_copy(update={"status": snapshot_status})


@router.get("/market-macro", response_model=MarketGroupSnapshot)
async def get_market_macro(redis: RedisDep) -> MarketGroupSnapshot:
    return await _get_market_snapshot_or_503(redis, "macro")


@router.get("/market-assets", response_model=MarketGroupSnapshot)
async def get_market_assets(redis: RedisDep) -> MarketGroupSnapshot:
    return await _get_market_snapshot_or_503(redis, "assets")

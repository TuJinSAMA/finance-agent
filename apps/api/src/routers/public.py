from fastapi import APIRouter

from src.schemas.public_board import PublicMarketBoardResponse
from src.services.public_board import get_public_market_board

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/market-board", response_model=PublicMarketBoardResponse)
async def get_market_board() -> PublicMarketBoardResponse:
    return await get_public_market_board()

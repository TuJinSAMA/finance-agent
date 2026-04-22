import json
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.agents.decision_chain.graph import TradingDecisionChain

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/decision-chain", tags=["decision-chain"])


class DecisionChainRequest(BaseModel):
    ticker: str
    trade_date: Optional[str] = None


class DecisionChainResponse(BaseModel):
    status: str
    ticker: str
    rating: str
    trade_date: str


@router.post("/run", response_class=EventSourceResponse)
async def run_decision_chain(request: DecisionChainRequest):
    """Run the investment decision chain and stream stage-by-stage results via SSE."""
    trade_date = request.trade_date or date.today().strftime("%Y-%m-%d")
    chain = TradingDecisionChain()

    async def event_generator():
        try:
            stage_map = {
                "Market Analyst": "market_analyst",
                "Social Analyst": "social_analyst",
                "News Analyst": "news_analyst",
                "Fundamentals Analyst": "fundamentals_analyst",
                "Bull Researcher": "bull_researcher",
                "Bear Researcher": "bear_researcher",
                "Research Manager": "research_manager",
                "Trader": "trader",
                "Aggressive Analyst": "aggressive_analyst",
                "Conservative Analyst": "conservative_analyst",
                "Neutral Analyst": "neutral_analyst",
                "Portfolio Manager": "portfolio_manager",
            }

            async for event in chain.apropagate(request.ticker, trade_date):
                for node_name, node_state in event.items():
                    stage = stage_map.get(node_name, node_name)
                    yield {
                        "event": "stage_update",
                        "data": json.dumps({
                            "stage": stage,
                            "node": node_name,
                            "state_keys": list(node_state.keys()) if isinstance(node_state, dict) else None,
                        }, ensure_ascii=False),
                    }

            final_state = chain.curr_state
            if final_state:
                rating = chain.process_signal(final_state["final_trade_decision"])
                yield {
                    "event": "final_decision",
                    "data": json.dumps({
                        "content": final_state.get("final_trade_decision", ""),
                        "rating": rating,
                        "ticker": request.ticker,
                        "trade_date": trade_date,
                    }, ensure_ascii=False),
                }
                yield {
                    "event": "rating_extracted",
                    "data": json.dumps({"rating": rating}, ensure_ascii=False),
                }
        except Exception as e:
            logger.exception("Decision chain execution failed")
            yield {
                "event": "stage_error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.post("/run-sync", response_model=DecisionChainResponse)
async def run_decision_chain_sync(request: DecisionChainRequest):
    """Run the decision chain synchronously and return the final result."""
    trade_date = request.trade_date or date.today().strftime("%Y-%m-%d")
    chain = TradingDecisionChain()
    final_state, rating = chain.propagate(request.ticker, trade_date)

    return DecisionChainResponse(
        status="ok",
        ticker=request.ticker,
        rating=rating,
        trade_date=trade_date,
    )
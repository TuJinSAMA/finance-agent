from typing import Annotated
from langgraph.graph import MessagesState


class ChatAgentState(MessagesState):
    intent: Annotated[str, "Detected intent: 'pipeline' or 'chat'"]
    ticker: Annotated[str | None, "Ticker symbol if pipeline intent"]
    trade_date: Annotated[str | None, "Trade date if pipeline intent"]
    pipeline_stages: Annotated[list[dict], "Pipeline stage updates"]
    final_decision: Annotated[str | None, "Final trade decision text"]
    final_rating: Annotated[str | None, "Final rating: BUY/HOLD/SELL etc"]
    used_tokens: Annotated[int, "Token count used so far"]
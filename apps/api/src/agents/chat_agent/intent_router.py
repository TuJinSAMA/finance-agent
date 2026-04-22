import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.agents.decision_chain.config import decision_chain_config

INTENT_SYSTEM_PROMPT = """You are an intent classifier for a financial AI assistant. Based on the user's message and recent conversation context, classify the intent:

- Return "pipeline" if the user is asking to analyze a specific stock, requesting investment advice for a ticker, or wants a full trading decision. Also extract the ticker symbol.
- Return "chat" for everything else: greetings, general questions, follow-up discussion, clarifications, or when the user is just chatting.

Respond in EXACTLY this JSON format, no other text:
{"intent": "pipeline" | "chat", "ticker": "<symbol or null>", "trade_date": "<YYYY-MM-DD or null>"}

Examples:
- "分析茅台" -> {"intent": "pipeline", "ticker": "600519", "trade_date": null}
- "Should I buy AAPL?" -> {"intent": "pipeline", "ticker": "AAPL", "trade_date": null}
- "What is RSI?" -> {"intent": "chat", "ticker": null, "trade_date": null}
- "Tell me more about the risk" -> {"intent": "chat", "ticker": null, "trade_date": null}
"""


def classify_intent(messages: list, llm: ChatOpenAI | None = None) -> dict:
    """Classify user intent from recent messages.

    Args:
        messages: Recent conversation messages (last 3-5).
        llm: Optional LLM instance. Defaults to quick_think_llm.

    Returns:
        Dict with keys: intent, ticker, trade_date.
    """
    if llm is None:
        llm = ChatOpenAI(
            model=decision_chain_config.quick_think_llm,
            openai_api_key=decision_chain_config.openrouter_api_key,
            openai_api_base=decision_chain_config.openrouter_base_url,
            temperature=0,
        )

    recent = messages[-5:] if len(messages) > 5 else messages
    recent_text = "\n".join(
        f"{m.type}: {m.content}" for m in recent if hasattr(m, "content")
    )

    response = llm.invoke([
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=f"Classify intent:\n\n{recent_text}"),
    ])

    try:
        result = json.loads(response.content.strip())
        if result.get("intent") not in ("pipeline", "chat"):
            result["intent"] = "chat"
        return {
            "intent": result.get("intent", "chat"),
            "ticker": result.get("ticker"),
            "trade_date": result.get("trade_date"),
        }
    except (json.JSONDecodeError, KeyError):
        return {"intent": "chat", "ticker": None, "trade_date": None}
from datetime import date
from langgraph.graph import StateGraph, END
from src.agents.chat_agent.state import ChatAgentState
from src.agents.decision_chain.graph import TradingDecisionChain
from src.agents.decision_chain.config import decision_chain_config

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage


def route_intent(state: ChatAgentState) -> str:
    if state.get("intent") == "pipeline":
        return "pipeline"
    return "chat"


def chat_node(state: ChatAgentState) -> dict:
    llm = ChatOpenAI(
        model=decision_chain_config.quick_think_llm,
        openai_api_key=decision_chain_config.openrouter_api_key,
        openai_api_base=decision_chain_config.openrouter_base_url,
        temperature=0.7,
    )

    system_prompt = (
        "You are AlphaDesk, a knowledgeable financial AI assistant. "
        "You help users understand stocks, markets, and investment concepts. "
        "You provide thoughtful, balanced analysis and always note risks. "
        "Write your entire response in Chinese (中文). "
        "If users ask about a specific stock analysis, suggest they ask for a full analysis "
        "by mentioning the stock ticker directly."
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = llm.invoke(messages)

    token_count = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        token_count = response.usage_metadata.get("total_tokens", 0)

    return {
        "messages": [response],
        "used_tokens": state.get("used_tokens", 0) + token_count,
    }


def pipeline_node(state: ChatAgentState) -> dict:
    ticker = state.get("ticker", "")
    trade_date = state.get("trade_date") or date.today().strftime("%Y-%m-%d")

    chain = TradingDecisionChain()
    stage_updates = []
    final_decision = None
    final_rating = None

    import asyncio

    async def run_pipeline():
        nonlocal final_decision, final_rating
        async for event in chain.apropagate(ticker, trade_date):
            for node_name, node_state in event.items():
                stage_name = _map_node_to_stage(node_name)
                stage_updates.append({
                    "stage": stage_name,
                    "node": node_name,
                    "progress": f"{len(stage_updates) + 1}/12",
                })

        if chain.curr_state:
            final_decision = chain.curr_state.get("final_trade_decision", "")
            final_rating = chain.process_signal(final_decision)

    try:
        asyncio.run(run_pipeline())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_pipeline())

    token_count = 0
    if chain.curr_state and "messages" in chain.curr_state:
        for msg in chain.curr_state["messages"]:
            if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                token_count += msg.usage_metadata.get("total_tokens", 0)

    decision_summary = f"## Investment Decision: {ticker}\n\n"
    decision_summary += f"**Rating: {final_rating}**\n\n"
    decision_summary += final_decision or "No decision generated."
    decision_summary += f"\n\n*Analysis date: {trade_date}*"

    ai_message = AIMessage(content=decision_summary)

    return {
        "messages": [ai_message],
        "pipeline_stages": stage_updates,
        "final_decision": final_decision,
        "final_rating": final_rating,
        "used_tokens": state.get("used_tokens", 0) + token_count,
    }


def _map_node_to_stage(node_name: str) -> str:
    mapping = {
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
    return mapping.get(node_name, node_name.lower().replace(" ", "_"))


def build_chat_graph() -> StateGraph:
    graph = StateGraph(ChatAgentState)

    graph.add_node("chat", chat_node)
    graph.add_node("pipeline", pipeline_node)

    graph.set_conditional_entry_point(
        route_intent,
        {"chat": "chat", "pipeline": "pipeline"},
    )

    graph.add_edge("chat", END)
    graph.add_edge("pipeline", END)

    return graph
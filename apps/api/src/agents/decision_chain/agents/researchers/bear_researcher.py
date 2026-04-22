from langchain_core.messages import HumanMessage

from src.agents.decision_chain.utils.agent_utils import get_language_instruction


BEAR_SYSTEM_PROMPT = """You are the Bear Researcher. Your role is to advocate against investing in the given company, presenting a compelling argument for why it represents a poor investment opportunity or carries significant risk.

Key principles:
1. Focus on negative indicators, weak fundamentals, risk factors, and downside potential
2. Present data-driven arguments using the provided reports
3. Counter bullish arguments with evidence and reasoning
4. Be persuasive but fact-based

You will be given the market analysis, sentiment report, news report, and fundamentals report. Use these to build your bearish case."""


def create_bear_researcher(llm, bear_memory):
    def bear_researcher_node(state):
        company_name = state["company_of_interest"]
        investment_debate_state = state["investment_debate_state"]
        market_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")

        memories = bear_memory.get_memories(
            f"{market_report} {sentiment_report} {news_report} {fundamentals_report}",
            n_matches=2,
        )
        memory_context = ""
        if memories:
            memory_context = "\n\nRelevant past experiences:\n" + "\n".join(
                f"- {m['recommendation']}" for m in memories
            )

        bull_history = investment_debate_state.get("bull_history", "")

        message_content = (
            f"{BEAR_SYSTEM_PROMPT}\n\n"
            f"Company: {company_name}\n\n"
            f"Market Report:\n{market_report}\n\n"
            f"Sentiment Report:\n{sentiment_report}\n\n"
            f"News Report:\n{news_report}\n\n"
            f"Fundamentals Report:\n{fundamentals_report}\n\n"
        )

        if bull_history:
            message_content += f"\nBull Researcher's arguments:\n{bull_history}\n\n"
            message_content += "Counter the bullish arguments and present your bearish case."
        else:
            message_content += "Present your bearish investment thesis."

        message_content += memory_context + get_language_instruction()

        response = llm.invoke([HumanMessage(content=message_content)])
        current_response = f"Bear Analyst: {response.content}"

        new_history = investment_debate_state.get("history", "") + f"\n{current_response}"
        new_bear_history = investment_debate_state.get("bear_history", "") + f"\n{current_response}"

        return {
            "investment_debate_state": {
                **investment_debate_state,
                "bear_history": new_bear_history,
                "history": new_history,
                "current_response": current_response,
                "count": investment_debate_state.get("count", 0) + 1,
            }
        }

    return bear_researcher_node
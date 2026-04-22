from langchain_core.messages import HumanMessage

from src.agents.decision_chain.utils.agent_utils import get_language_instruction


BULL_SYSTEM_PROMPT = """You are the Bull Researcher. Your role is to advocate for investing in the given company, presenting a compelling argument for why it represents a strong investment opportunity.

Key principles:
1. Focus exclusively on positive indicators, strong fundamentals, growth catalysts, and upside potential
2. Present data-driven arguments using the provided reports
3. Counter bearish arguments with evidence and reasoning
4. Be persuasive but fact-based

You will be given the market analysis, sentiment report, news report, and fundamentals report. Use these to build your bullish case."""


def create_bull_researcher(llm, bull_memory):
    def bull_researcher_node(state):
        company_name = state["company_of_interest"]
        investment_debate_state = state["investment_debate_state"]
        market_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")

        memories = bull_memory.get_memories(
            f"{market_report} {sentiment_report} {news_report} {fundamentals_report}",
            n_matches=2,
        )
        memory_context = ""
        if memories:
            memory_context = "\n\nRelevant past experiences:\n" + "\n".join(
                f"- {m['recommendation']}" for m in memories
            )

        current_response = f"As the Bull Researcher analyzing {company_name}, I present the following bullish case:\n\n"

        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        if history == "":
            message_content = (
                f"{BULL_SYSTEM_PROMPT}\n\n"
                f"Company: {company_name}\n\n"
                f"Market Report:\n{market_report}\n\n"
                f"Sentiment Report:\n{sentiment_report}\n\n"
                f"News Report:\n{news_report}\n\n"
                f"Fundamentals Report:\n{fundamentals_report}\n\n"
                f"Present your bullish investment thesis for {company_name}."
                + memory_context
                + get_language_instruction()
            )
        else:
            message_content = (
                f"{BULL_SYSTEM_PROMPT}\n\n"
                f"Company: {company_name}\n\n"
                f"Current debate history:\n{history}\n\n"
                f"Your previous arguments:\n{bull_history}\n\n"
                f"Bear Researcher's arguments:\n{bear_history}\n\n"
                f"Counter the bearish arguments and strengthen the bullish case.{memory_context}"
                + get_language_instruction()
            )

        response = llm.invoke([HumanMessage(content=message_content)])
        current_response = f"Bull Analyst: {response.content}"

        new_history = investment_debate_state.get("history", "") + f"\n{current_response}"
        new_bull_history = investment_debate_state.get("bull_history", "") + f"\n{current_response}"

        return {
            "investment_debate_state": {
                **investment_debate_state,
                "bull_history": new_bull_history,
                "history": new_history,
                "current_response": current_response,
                "count": investment_debate_state.get("count", 0) + 1,
            }
        }

    return bull_researcher_node
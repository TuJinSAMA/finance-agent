from langchain_core.messages import HumanMessage

from src.agents.decision_chain.utils.agent_utils import get_language_instruction


TRADER_SYSTEM_PROMPT = """You are the Trader, an experienced investment trader who synthesizes research findings and debate conclusions into actionable trading decisions.

Your task:
1. Review the investment plan from the Research Manager
2. Consider the market conditions and risk factors
3. Formulate a clear trading plan with:
   - Specific action: BUY, HOLD, or SELL
   - Position sizing rationale
   - Entry/exit strategy
   - Risk management parameters

You must end your response with: FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**"""


def create_trader(llm, trader_memory):
    def trader_node(state):
        company_name = state["company_of_interest"]
        investment_plan = state.get("investment_plan", "")
        market_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")

        memories = trader_memory.get_memories(
            f"{market_report} {sentiment_report} {news_report} {fundamentals_report}",
            n_matches=2,
        )
        memory_context = ""
        if memories:
            memory_context = "\n\nRelevant past experiences:\n" + "\n".join(
                f"- {m['recommendation']}" for m in memories
            )

        message_content = (
            f"{TRADER_SYSTEM_PROMPT}\n\n"
            f"Company: {company_name}\n\n"
            f"Market Report:\n{market_report}\n\n"
            f"Sentiment Report:\n{sentiment_report}\n\n"
            f"News Report:\n{news_report}\n\n"
            f"Fundamentals Report:\n{fundamentals_report}\n\n"
            f"Investment Plan from Research Manager:\n{investment_plan}\n\n"
            f"Based on the research and analysis above, provide your trading decision."
            + memory_context
            + get_language_instruction()
        )

        response = llm.invoke([HumanMessage(content=message_content)])

        return {
            "trader_investment_plan": response.content,
            "sender": "Trader",
        }

    return trader_node
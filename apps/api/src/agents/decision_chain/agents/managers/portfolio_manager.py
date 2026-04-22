from langchain_core.messages import HumanMessage

from src.agents.decision_chain.utils.agent_utils import get_language_instruction


PORTFOLIO_MANAGER_SYSTEM_PROMPT = """You are the Portfolio Manager, a senior risk analyst responsible for making the final trading decision based on the debate between aggressive, conservative, and neutral risk analysts.

Your task:
1. Review the risk debate carefully
2. Consider the aggressive, conservative, and neutral perspectives
3. Weigh the evidence and arguments from all sides
4. Make a final trading decision

Your final decision must be one of: BUY, OVERWEIGHT, HOLD, UNDERWEIGHT, or SELL.

Provide a comprehensive justification for your decision, including:
- Key factors considered
- Risk assessment
- Expected return/risk ratio
- Recommended position size (if applicable)
- Any caveats or conditions"""


def create_portfolio_manager(llm, portfolio_manager_memory):
    def portfolio_manager_node(state):
        company_name = state["company_of_interest"]
        risk_debate_state = state.get("risk_debate_state", {})
        market_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")

        aggressive_history = risk_debate_state.get("aggressive_history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        memories = portfolio_manager_memory.get_memories(
            f"{market_report} {sentiment_report} {news_report} {fundamentals_report}",
            n_matches=2,
        )
        memory_context = ""
        if memories:
            memory_context = "\n\nRelevant past experiences:\n" + "\n".join(
                f"- {m['recommendation']}" for m in memories
            )

        message_content = (
            f"{PORTFOLIO_MANAGER_SYSTEM_PROMPT}\n\n"
            f"Company: {company_name}\n\n"
            f"Market Report:\n{market_report}\n\n"
            f"Sentiment Report:\n{sentiment_report}\n\n"
            f"News Report:\n{news_report}\n\n"
            f"Fundamentals Report:\n{fundamentals_report}\n\n"
            f"Investment Plan:\n{state.get('investment_plan', '')}\n\n"
            f"Trader's Plan:\n{state.get('trader_investment_plan', '')}\n\n"
            f"Aggressive Arguments:\n{aggressive_history}\n\n"
            f"Conservative Arguments:\n{conservative_history}\n\n"
            f"Neutral Arguments:\n{neutral_history}\n\n"
            f"Based on all the above analysis and debate, make your final trading decision."
            + memory_context
            + get_language_instruction()
        )

        response = llm.invoke([HumanMessage(content=message_content)])

        return {
            "risk_debate_state": {
                **risk_debate_state,
                "judge_decision": response.content,
            },
            "final_trade_decision": response.content,
        }

    return portfolio_manager_node
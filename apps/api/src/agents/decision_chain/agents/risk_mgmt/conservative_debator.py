from langchain_core.messages import HumanMessage

from src.agents.decision_chain.utils.agent_utils import get_language_instruction


CONSERVATIVE_SYSTEM_PROMPT = """You are the Conservative Risk Analyst. Your role is to argue for lower risk, more defensive investment strategies.

Key principles:
1. Advocate for conservative, risk-averse investment positions
2. Focus on capital preservation and downside protection
3. Challenge aggressive viewpoints with caution, evidence-based arguments
4. Emphasize risk management, diversification, and hedging
5. Acknowledge but minimize upside potential claims

Be persuasive and data-driven in your arguments."""


def create_conservative_debator(llm):
    def conservative_debator_node(state):
        company_name = state["company_of_interest"]
        risk_debate_state = state.get("risk_debate_state", {})
        investment_plan = state.get("investment_plan", "")
        trader_plan = state.get("trader_investment_plan", "")

        aggressive_history = risk_debate_state.get("aggressive_history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")
        history = risk_debate_state.get("history", "")

        message_content = (
            f"{CONSERVATIVE_SYSTEM_PROMPT}\n\n"
            f"Company: {company_name}\n\n"
            f"Investment Plan:\n{investment_plan}\n\n"
            f"Trader's Plan:\n{trader_plan}\n\n"
        )

        if history:
            message_content += f"Debate History:\n{history}\n\n"
            if aggressive_history:
                message_content += f"Aggressive Arguments:\n{aggressive_history}\n\n"
            if neutral_history:
                message_content += f"Neutral Arguments:\n{neutral_history}\n\n"
            message_content += "Counter the arguments and present your conservative perspective."
        else:
            message_content += "Present your conservative risk perspective on this investment."

        message_content += get_language_instruction()

        response = llm.invoke([HumanMessage(content=message_content)])
        current_response = f"Conservative Analyst: {response.content}"

        new_history = risk_debate_state.get("history", "") + f"\n{current_response}"
        new_conservative_history = risk_debate_state.get("conservative_history", "") + f"\n{current_response}"

        return {
            "risk_debate_state": {
                **risk_debate_state,
                "conservative_history": new_conservative_history,
                "history": new_history,
                "current_conservative_response": current_response,
                "latest_speaker": "Conservative",
                "count": risk_debate_state.get("count", 0) + 1,
            }
        }

    return conservative_debator_node
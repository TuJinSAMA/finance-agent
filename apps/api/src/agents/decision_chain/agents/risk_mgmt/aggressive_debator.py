from langchain_core.messages import HumanMessage

from src.agents.decision_chain.utils.agent_utils import get_language_instruction


AGGRESSIVE_SYSTEM_PROMPT = """You are the Aggressive Risk Analyst. Your role is to argue for higher risk, higher reward investment strategies.

Key principles:
1. Advocate for aggressive investment positions
2. Focus on potential upside and growth opportunities
3. Challenge conservative viewpoints with bold, evidence-based arguments
4. Consider leveraged positions, concentrated bets, or momentum plays
5. Acknowledge but minimize risk concerns

Be persuasive and data-driven in your arguments."""


def create_aggressive_debator(llm):
    def aggressive_debator_node(state):
        company_name = state["company_of_interest"]
        risk_debate_state = state.get("risk_debate_state", {})
        investment_plan = state.get("investment_plan", "")
        trader_plan = state.get("trader_investment_plan", "")

        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        message_content = (
            f"{AGGRESSIVE_SYSTEM_PROMPT}\n\n"
            f"Company: {company_name}\n\n"
            f"Investment Plan:\n{investment_plan}\n\n"
            f"Trader's Plan:\n{trader_plan}\n\n"
        )

        if history:
            message_content += f"Debate History:\n{history}\n\n"
            if conservative_history:
                message_content += f"Conservative Arguments:\n{conservative_history}\n\n"
            if neutral_history:
                message_content += f"Neutral Arguments:\n{neutral_history}\n\n"
            message_content += "Counter the arguments and present your aggressive perspective."
        else:
            message_content += "Present your aggressive risk perspective on this investment."

        message_content += get_language_instruction()

        response = llm.invoke([HumanMessage(content=message_content)])
        current_response = f"Aggressive Analyst: {response.content}"

        new_history = risk_debate_state.get("history", "") + f"\n{current_response}"
        new_aggressive_history = risk_debate_state.get("aggressive_history", "") + f"\n{current_response}"

        return {
            "risk_debate_state": {
                **risk_debate_state,
                "aggressive_history": new_aggressive_history,
                "history": new_history,
                "current_aggressive_response": current_response,
                "latest_speaker": "Aggressive",
                "count": risk_debate_state.get("count", 0) + 1,
            }
        }

    return aggressive_debator_node
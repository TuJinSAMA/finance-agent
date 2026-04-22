from langchain_core.messages import HumanMessage

from src.agents.decision_chain.utils.agent_utils import get_language_instruction


NEUTRAL_SYSTEM_PROMPT = """You are the Neutral Risk Analyst. Your role is to provide a balanced, objective assessment of the investment opportunity.

Key principles:
1. Provide balanced analysis weighing both upside and downside
2. Consider risk-reward trade-offs objectively
3. Moderate between aggressive and conservative viewpoints
4. Focus on data-driven, evidence-based assessment
5. Highlight areas of uncertainty that need more information

Be analytical and impartial in your arguments."""


def create_neutral_debator(llm):
    def neutral_debator_node(state):
        company_name = state["company_of_interest"]
        risk_debate_state = state.get("risk_debate_state", {})
        investment_plan = state.get("investment_plan", "")
        trader_plan = state.get("trader_investment_plan", "")

        aggressive_history = risk_debate_state.get("aggressive_history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")
        history = risk_debate_state.get("history", "")

        message_content = (
            f"{NEUTRAL_SYSTEM_PROMPT}\n\n"
            f"Company: {company_name}\n\n"
            f"Investment Plan:\n{investment_plan}\n\n"
            f"Trader's Plan:\n{trader_plan}\n\n"
        )

        if history:
            message_content += f"Debate History:\n{history}\n\n"
            if aggressive_history:
                message_content += f"Aggressive Arguments:\n{aggressive_history}\n\n"
            if conservative_history:
                message_content += f"Conservative Arguments:\n{conservative_history}\n\n"
            message_content += "Provide your balanced, neutral perspective on this investment."
        else:
            message_content += "Present your balanced, neutral risk perspective on this investment."

        message_content += get_language_instruction()

        response = llm.invoke([HumanMessage(content=message_content)])
        current_response = f"Neutral Analyst: {response.content}"

        new_history = risk_debate_state.get("history", "") + f"\n{current_response}"
        new_neutral_history = risk_debate_state.get("neutral_history", "") + f"\n{current_response}"

        return {
            "risk_debate_state": {
                **risk_debate_state,
                "neutral_history": new_neutral_history,
                "history": new_history,
                "current_neutral_response": current_response,
                "latest_speaker": "Neutral",
                "count": risk_debate_state.get("count", 0) + 1,
            }
        }

    return neutral_debator_node
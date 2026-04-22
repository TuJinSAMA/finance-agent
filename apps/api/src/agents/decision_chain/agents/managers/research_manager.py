from langchain_core.messages import HumanMessage

from src.agents.decision_chain.utils.agent_utils import get_language_instruction


RESEARCH_MANAGER_SYSTEM_PROMPT = """You are the Research Manager, a senior investment analyst responsible for synthesizing the debate between Bull and Bear researchers and making a final investment recommendation.

Your task:
1. Review the bull and bear arguments carefully
2. Weigh the evidence presented by both sides
3. Consider the objective data from all reports
4. Make a clear, well-reasoned investment recommendation

Your recommendation should be one of: BUY, HOLD, or SELL, with supporting reasoning."""


def create_research_manager(llm, invest_judge_memory):
    def research_manager_node(state):
        company_name = state["company_of_interest"]
        investment_debate_state = state["investment_debate_state"]
        market_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")

        bull_history = investment_debate_state.get("bull_history", "")
        bear_history = investment_debate_state.get("bear_history", "")
        debate_history = investment_debate_state.get("history", "")

        memories = invest_judge_memory.get_memories(
            f"{market_report} {sentiment_report} {news_report} {fundamentals_report}",
            n_matches=2,
        )
        memory_context = ""
        if memories:
            memory_context = "\n\nRelevant past experiences:\n" + "\n".join(
                f"- {m['recommendation']}" for m in memories
            )

        message_content = (
            f"{RESEARCH_MANAGER_SYSTEM_PROMPT}\n\n"
            f"Company: {company_name}\n\n"
            f"Market Report:\n{market_report}\n\n"
            f"Sentiment Report:\n{sentiment_report}\n\n"
            f"News Report:\n{news_report}\n\n"
            f"Fundamentals Report:\n{fundamentals_report}\n\n"
            f"Full Debate History:\n{debate_history}\n\n"
            f"Bull Arguments:\n{bull_history}\n\n"
            f"Bear Arguments:\n{bear_history}\n\n"
            f"Based on the above analysis and debate, provide your final investment recommendation."
            + memory_context
            + get_language_instruction()
        )

        response = llm.invoke([HumanMessage(content=message_content)])

        return {
            "investment_debate_state": {
                **investment_debate_state,
                "judge_decision": response.content,
            },
            "investment_plan": response.content,
        }

    return research_manager_node
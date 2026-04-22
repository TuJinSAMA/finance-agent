import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.decision_chain.agents import (
    create_market_analyst,
    create_social_media_analyst,
    create_news_analyst,
    create_fundamentals_analyst,
    create_bull_researcher,
    create_bear_researcher,
    create_research_manager,
    create_portfolio_manager,
    create_trader,
    create_aggressive_debator,
    create_conservative_debator,
    create_neutral_debator,
)
from src.agents.decision_chain.conditional_logic import ConditionalLogic
from src.agents.decision_chain.config import decision_chain_config
from src.agents.decision_chain.propagation import Propagator
from src.agents.decision_chain.reflection import Reflector
from src.agents.decision_chain.signal_processing import SignalProcessor
from src.agents.decision_chain.state import AgentState
from src.agents.decision_chain.tools import (
    get_stock_data,
    get_indicators,
    get_news,
    get_global_news,
    get_insider_transactions,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
)
from src.agents.decision_chain.utils.agent_utils import create_msg_delete
from src.agents.decision_chain.utils.memory import FinancialSituationMemory

logger = logging.getLogger(__name__)


class TradingDecisionChain:
    def __init__(
        self,
        selected_analysts: list[str] | None = None,
        config: dict | None = None,
    ):
        if selected_analysts is None:
            selected_analysts = ["market", "social", "news", "fundamentals"]
        if not selected_analysts:
            raise ValueError("At least one analyst must be selected")

        self.config = config or decision_chain_config.model_dump()
        self.selected_analysts = selected_analysts

        os.makedirs(self.config.get("results_dir", "./decision_results"), exist_ok=True)

        deep_client = ChatOpenAI(
            openai_api_key=self.config.get("openrouter_api_key") or decision_chain_config.openrouter_api_key,
            openai_api_base=self.config.get("openrouter_base_url", decision_chain_config.openrouter_base_url),
            model=self.config.get("deep_think_llm", decision_chain_config.deep_think_llm),
            temperature=0.3,
        )
        quick_client = ChatOpenAI(
            openai_api_key=self.config.get("openrouter_api_key") or decision_chain_config.openrouter_api_key,
            openai_api_base=self.config.get("openrouter_base_url", decision_chain_config.openrouter_base_url),
            model=self.config.get("quick_think_llm", decision_chain_config.quick_think_llm),
            temperature=0.3,
        )
        self.deep_thinking_llm = deep_client
        self.quick_thinking_llm = quick_client

        db_dir = os.path.join(self.config.get("results_dir", "./decision_results"), "memories")
        self.bull_memory = FinancialSituationMemory("bull_memory", db_dir=db_dir)
        self.bear_memory = FinancialSituationMemory("bear_memory", db_dir=db_dir)
        self.trader_memory = FinancialSituationMemory("trader_memory", db_dir=db_dir)
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", db_dir=db_dir)
        self.portfolio_manager_memory = FinancialSituationMemory("portfolio_manager_memory", db_dir=db_dir)

        self.tool_nodes = self._create_tool_nodes()

        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config.get("max_debate_rounds", decision_chain_config.max_debate_rounds),
            max_risk_discuss_rounds=self.config.get("max_risk_discuss_rounds", decision_chain_config.max_risk_discuss_rounds),
        )

        self._build_graph()

        self.propagator = Propagator(max_recur_limit=self.config.get("max_recur_limit", decision_chain_config.max_recur_limit))
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        self.curr_state = None
        self.ticker = None

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        return {
            "market": ToolNode([get_stock_data, get_indicators]),
            "social": ToolNode([get_news]),
            "news": ToolNode([get_news, get_global_news, get_insider_transactions]),
            "fundamentals": ToolNode([get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement]),
        }

    def _build_graph(self):
        graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.portfolio_manager_memory,
            self.conditional_logic,
        )
        self.graph = graph_setup.setup_graph(self.selected_analysts)

    def propagate(self, company_name: str, trade_date: str) -> Tuple[dict, str]:
        self.ticker = company_name
        init_state = self.propagator.create_initial_state(company_name, trade_date)
        args = self.propagator.get_graph_args()

        final_state = self.graph.invoke(init_state, **args)
        self.curr_state = final_state
        self._log_state(trade_date, final_state)

        return final_state, self.process_signal(final_state["final_trade_decision"])

    async def apropagate(self, company_name: str, trade_date: str):
        self.ticker = company_name
        init_state = self.propagator.create_initial_state(company_name, trade_date)
        args = self.propagator.get_graph_args()

        async for event in self.graph.astream(init_state, **args):
            yield event

    def process_signal(self, full_signal: str) -> str:
        return self.signal_processor.process_signal(full_signal)

    def _log_state(self, trade_date, final_state):
        log_data = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"]["current_response"],
                "judge_decision": final_state["investment_debate_state"]["judge_decision"],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        directory = Path(self.config.get("results_dir", "./decision_results")) / (self.ticker or "unknown") / "decision_chain_logs"
        directory.mkdir(parents=True, exist_ok=True)
        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=4, ensure_ascii=False)

    def reflect_and_remember(self, returns_losses):
        self.reflector.reflect_bull_researcher(self.curr_state, returns_losses, self.bull_memory)
        self.reflector.reflect_bear_researcher(self.curr_state, returns_losses, self.bear_memory)
        self.reflector.reflect_trader(self.curr_state, returns_losses, self.trader_memory)
        self.reflector.reflect_invest_judge(self.curr_state, returns_losses, self.invest_judge_memory)
        self.reflector.reflect_portfolio_manager(self.curr_state, returns_losses, self.portfolio_manager_memory)


class GraphSetup:
    def __init__(
        self,
        quick_thinking_llm,
        deep_thinking_llm,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        portfolio_manager_memory,
        conditional_logic: ConditionalLogic,
    ):
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.portfolio_manager_memory = portfolio_manager_memory
        self.conditional_logic = conditional_logic

    def setup_graph(self, selected_analysts=None):
        if selected_analysts is None:
            selected_analysts = ["market", "social", "news", "fundamentals"]
        if len(selected_analysts) == 0:
            raise ValueError("At least one analyst must be selected")

        analyst_nodes = {}
        delete_nodes = {}
        analyst_tool_nodes = {}

        analyst_creators = {
            "market": create_market_analyst,
            "social": create_social_media_analyst,
            "news": create_news_analyst,
            "fundamentals": create_fundamentals_analyst,
        }

        for analyst_type in selected_analysts:
            if analyst_type not in analyst_creators:
                raise ValueError(f"Unknown analyst type: {analyst_type}")
            analyst_nodes[analyst_type] = analyst_creators[analyst_type](self.quick_thinking_llm)
            delete_nodes[analyst_type] = create_msg_delete()
            analyst_tool_nodes[analyst_type] = self.tool_nodes[analyst_type]

        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm, self.bull_memory)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm, self.bear_memory)
        research_manager_node = create_research_manager(self.deep_thinking_llm, self.invest_judge_memory)
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm, self.portfolio_manager_memory)

        workflow = StateGraph(AgentState)

        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type])
            workflow.add_node(f"tools_{analyst_type}", analyst_tool_nodes[analyst_type])

        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i + 1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Conservative Analyst": "Conservative Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Neutral Analyst": "Neutral Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Aggressive Analyst": "Aggressive Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_edge("Portfolio Manager", END)

        return workflow.compile()
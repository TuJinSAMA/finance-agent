import json
import logging
from datetime import date
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import AIMessage

from src.agents.chat_agent.state import ChatAgentState
from src.agents.chat_agent.graph import build_chat_graph

logger = logging.getLogger(__name__)

SQLITE_CHECKPOINT_DIR = Path(__file__).parent.parent.parent.parent / "chat_checkpoints"


class ChatAgent:
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        SQLITE_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        db_path = SQLITE_CHECKPOINT_DIR / f"{thread_id}.db"
        self.memory = SqliteSaver.from_conn_string(str(db_path))
        self.graph = build_chat_graph().compile(checkpointer=self.memory)

    def _build_initial_state(self, user_message: str, intent_result: dict) -> ChatAgentState:
        return {
            "messages": [],
            "intent": intent_result["intent"],
            "ticker": intent_result.get("ticker"),
            "trade_date": intent_result.get("trade_date") or date.today().strftime("%Y-%m-%d"),
            "pipeline_stages": [],
            "final_decision": None,
            "final_rating": None,
            "used_tokens": 0,
        }

    async def astream_chat(self, user_message: str, intent_result: dict):
        """Stream the agent response, yielding SSE-compatible event dicts.

        The caller should provide the intent_result from classify_intent.
        This method streams events for:
        - Pipeline stage updates
        - Token-by-token chat responses (if chat node)
        - Final decision result
        - Context usage updates
        """
        config = {"configurable": {"thread_id": self.thread_id}}

        initial_state = self._build_initial_state(user_message, intent_result)

        if intent_result["intent"] == "pipeline":
            async for event in self.graph.astream(
                initial_state, config=config, stream_mode="values"
            ):
                for node_name, node_state in event.items():
                    if node_name == "pipeline":
                        stages = node_state.get("pipeline_stages", [])
                        for stage in stages:
                            yield {
                                "event": "stage_update",
                                "data": json.dumps(stage, ensure_ascii=False),
                            }
                        if node_state.get("final_rating"):
                            yield {
                                "event": "final_decision",
                                "data": json.dumps({
                                    "content": node_state.get("final_decision", ""),
                                    "rating": node_state["final_rating"],
                                    "ticker": node_state.get("ticker", ""),
                                    "trade_date": node_state.get("trade_date", ""),
                                }, ensure_ascii=False),
                            }
                        used = node_state.get("used_tokens", 0)
                        yield {
                            "event": "context_usage",
                            "data": json.dumps({
                                "used_tokens": used,
                                "max_tokens": 128000,
                            }),
                        }
                    elif node_name == "chat":
                        messages = node_state.get("messages", [])
                        if messages:
                            last_msg = messages[-1]
                            if isinstance(last_msg, AIMessage):
                                yield {
                                    "event": "assistant_message",
                                    "data": json.dumps({
                                        "content": last_msg.content,
                                        "role": "assistant",
                                    }, ensure_ascii=False),
                                }
                        used = node_state.get("used_tokens", 0)
                        yield {
                            "event": "context_usage",
                            "data": json.dumps({
                                "used_tokens": used,
                                "max_tokens": 128000,
                            }),
                        }
        else:
            config_with_msg = {"configurable": {"thread_id": self.thread_id}}
            result = await self.graph.ainvoke(initial_state, config=config_with_msg)
            messages = result.get("messages", [])
            if messages:
                last_msg = messages[-1]
                if isinstance(last_msg, AIMessage):
                    yield {
                        "event": "assistant_message",
                        "data": json.dumps({
                            "content": last_msg.content,
                            "role": "assistant",
                        }, ensure_ascii=False),
                    }
            used = result.get("used_tokens", 0)
            yield {
                "event": "context_usage",
                "data": json.dumps({
                    "used_tokens": used,
                    "max_tokens": 128000,
                }),
            }

        yield {"event": "done", "data": json.dumps({"status": "complete"})}

    def clear_checkpoint(self):
        """Delete the checkpoint database for this thread."""
        db_path = SQLITE_CHECKPOINT_DIR / f"{self.thread_id}.db"
        if db_path.exists():
            db_path.unlink()
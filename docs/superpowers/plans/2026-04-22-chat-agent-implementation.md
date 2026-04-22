# Chat Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated chat page where users can converse with the Decision Chain Agent, with session management, persistent history, pipeline progress, context gauge, and context clearing.

**Architecture:** LangGraph `MemorySaver` (SQLite) manages conversation state per thread. A new `ChatAgent` wraps an intent-router graph that dispatches to either a `chat_node` (general Q&A) or `pipeline_node` (full DecisionChain). Backend stores session metadata and messages in PostgreSQL for frontend display. Frontend uses SSE streaming for real-time chat.

**Tech Stack:** Python 3.12+, LangGraph, LangChain, SQLAlchemy 2.0 (async), Pydantic v2, FastAPI, sse-starlette, Next.js 16, React 19, TypeScript, Tailwind CSS 4, Clerk auth

---

## File Structure

### Backend (new files)

```
apps/api/src/
├── models/
│   ├── chat_session.py            # ChatSession model
│   ├── chat_message.py           # ChatMessage model
│   └── __init__.py               # Update re-exports
├── schemas/
│   ├── chat.py                    # ChatSession + ChatMessage schemas
│   └── __init__.py               # Update re-exports
├── services/
│   ├── chat_session.py            # ChatSessionService
│   └── chat_agent.py             # ChatAgentService (orchestration)
├── agents/chat_agent/
│   ├── __init__.py                # Exports ChatAgent
│   ├── agent.py                  # ChatAgent class (main entry)
│   ├── intent_router.py           # Intent classification via LLM
│   ├── graph.py                  # LangGraph state + routing graph
│   └── state.py                  # ChatAgentState TypedDict
├── routers/
│   └── chat.py                   # FastAPI router (all chat endpoints)
└── dependencies.py                # Add chat service deps
```

### Frontend (new files)

```
apps/web/src/
├── app/[locale]/recommendations/chat/
│   └── page.tsx                   # Chat page entry
├── components/chat/
│   ├── ChatLayout.tsx             # Main layout: sidebar + chat area
│   ├── SessionSidebar.tsx         # Session list
│   ├── SessionItem.tsx            # Single session row
│   ├── ChatArea.tsx               # Messages + input container
│   ├── MessageList.tsx            # Scrollable message list
│   ├── MessageBubble.tsx          # Single message (user/assistant)
│   ├── PipelineProgress.tsx       # Stage step indicator
│   ├── ContextGauge.tsx           # Context window progress bar
│   ├── ChatInput.tsx              # Text input + send
│   └── NewSessionButton.tsx       # New chat button
├── hooks/
│   ├── useChatSession.ts          # Session CRUD hook
│   └── useChatMessages.ts         # Message sending + SSE stream
├── lib/
│   └── chat-sse.ts                # SSE client for chat
└── types/
    └── chat.ts                    # TypeScript types for chat API
```

### Frontend (modified files)

```
apps/web/src/app/[locale]/recommendations/layout.tsx  # Add "Chat" nav item
apps/web/src/types/api.ts                              # (optional, types in chat.ts)
```

---

### Task 1: Create ChatAgent state and intent router

**Files:**
- Create: `apps/api/src/agents/chat_agent/__init__.py`
- Create: `apps/api/src/agents/chat_agent/state.py`
- Create: `apps/api/src/agents/chat_agent/intent_router.py`

- [ ] **Step 1: Create `__init__.py`**

```python
from src.agents.chat_agent.agent import ChatAgent

__all__ = ["ChatAgent"]
```

- [ ] **Step 2: Create `state.py`**

```python
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import MessagesState


class ChatAgentState(MessagesState):
    intent: Annotated[str, "Detected intent: 'pipeline' or 'chat'"]
    ticker: Annotated[str | None, "Ticker symbol if pipeline intent"]
    trade_date: Annotated[str | None, "Trade date if pipeline intent"]
    pipeline_stages: Annotated[list[dict], "Pipeline stage updates"]
    final_decision: Annotated[str | None, "Final trade decision text"]
    final_rating: Annotated[str | None, "Final rating: BUY/HOLD/SELL etc"]
    used_tokens: Annotated[int, "Token count used so far"]
```

- [ ] **Step 3: Create `intent_router.py`**

```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.agents.decision_chain.config import decision_chain_config

INTENT_SYSTEM_PROMPT = """You are an intent classifier for a financial AI assistant. Based on the user's message and recent conversation context, classify the intent:

- Return "pipeline" if the user is asking to analyze a specific stock, requesting investment advice for a ticker, or wants a full trading decision. Also extract the ticker symbol.
- Return "chat" for everything else: greetings, general questions, follow-up discussion, clarifications, or when the user is just chatting.

Respond in EXACTLY this JSON format, no other text:
{"intent": "pipeline" | "chat", "ticker": "<symbol or null>", "trade_date": "<YYYY-MM-DD or null>"}

Examples:
- "分析茅台" -> {"intent": "pipeline", "ticker": "600519", "trade_date": null}
- "Should I buy AAPL?" -> {"intent": "pipeline", "ticker": "AAPL", "trade_date": null}
- "What is RSI?" -> {"intent": "chat", "ticker": null, "trade_date": null}
- "Tell me more about the risk" -> {"intent": "chat", "ticker": null, "trade_date": null}
"""


def classify_intent(messages: list, llm: ChatOpenAI | None = None) -> dict:
    """Classify user intent from recent messages.

    Args:
        messages: Recent conversation messages (last 3-5).
        llm: Optional LLM instance. Defaults to quick_think_llm.

    Returns:
        Dict with keys: intent, ticker, trade_date.
    """
    if llm is None:
        llm = ChatOpenAI(
            model=decision_chain_config.quick_think_llm,
            openai_api_key=decision_chain_config.openrouter_api_key,
            openai_api_base=decision_chain_config.openrouter_base_url,
            temperature=0,
        )

    recent = messages[-5:] if len(messages) > 5 else messages
    recent_text = "\n".join(
        f"{m.type}: {m.content}" for m in recent if hasattr(m, "content")
    )

    response = llm.invoke([
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=f"Classify intent:\n\n{recent_text}"),
    ])

    import json
    try:
        result = json.loads(response.content.strip())
        if result.get("intent") not in ("pipeline", "chat"):
            result["intent"] = "chat"
        return {
            "intent": result.get("intent", "chat"),
            "ticker": result.get("ticker"),
            "trade_date": result.get("trade_date"),
        }
    except (json.JSONDecodeError, KeyError):
        return {"intent": "chat", "ticker": None, "trade_date": None}
```

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/agents/chat_agent/
git commit -m "feat(chat-agent): add state and intent router"
```

---

### Task 2: Create ChatAgent graph and agent class

**Files:**
- Create: `apps/api/src/agents/chat_agent/graph.py`
- Create: `apps/api/src/agents/chat_agent/agent.py`

- [ ] **Step 1: Create `graph.py`**

```python
from datetime import date
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from src.agents.chat_agent.state import ChatAgentState
from src.agents.chat_agent.intent_router import classify_intent
from src.agents.decision_chain.graph import TradingDecisionChain
from src.agents.decision_chain.config import decision_chain_config

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage


def route_intent(state: ChatAgentState) -> str:
    if state.get("intent") == "pipeline":
        return "pipeline"
    return "chat"


def chat_node(state: ChatAgentState) -> dict:
    llm = ChatOpenAI(
        model=decision_chain_config.quick_think_llm,
        openai_api_key=decision_chain_config.openrouter_api_key,
        openai_api_base=decision_chain_config.openrouter_base_url,
        temperature=0.7,
    )

    system_prompt = (
        "You are AlphaDesk, a knowledgeable financial AI assistant. "
        "You help users understand stocks, markets, and investment concepts. "
        "You provide thoughtful, balanced analysis and always note risks. "
        "Write your entire response in Chinese (中文). "
        "If users ask about a specific stock analysis, suggest they ask for a full analysis "
        "by mentioning the stock ticker directly."
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = llm.invoke(messages)

    token_count = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        token_count = response.usage_metadata.get("total_tokens", 0)

    return {
        "messages": [response],
        "used_tokens": state.get("used_tokens", 0) + token_count,
    }


def pipeline_node(state: ChatAgentState) -> dict:
    ticker = state.get("ticker", "")
    trade_date = state.get("trade_date") or date.today().strftime("%Y-%m-%d")

    chain = TradingDecisionChain()
    stage_updates = []
    final_decision = None
    final_rating = None

    import asyncio

    async def run_pipeline():
        nonlocal final_decision, final_rating
        async for event in chain.apropagate(ticker, trade_date):
            for node_name, node_state in event.items():
                stage_name = _map_node_to_stage(node_name)
                stage_updates.append({
                    "stage": stage_name,
                    "node": node_name,
                    "progress": f"{len(stage_updates) + 1}/12",
                })

        if chain.curr_state:
            final_decision = chain.curr_state.get("final_trade_decision", "")
            final_rating = chain.process_signal(final_decision)

    try:
        asyncio.run(run_pipeline())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_pipeline())

    token_count = 0
    if chain.curr_state and "messages" in chain.curr_state:
        for msg in chain.curr_state["messages"]:
            if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                token_count += msg.usage_metadata.get("total_tokens", 0)

    decision_summary = f"## Investment Decision: {ticker}\n\n"
    decision_summary += f"**Rating: {final_rating}**\n\n"
    decision_summary += final_decision or "No decision generated."
    decision_summary += f"\n\n*Analysis date: {trade_date}*"

    ai_message = AIMessage(content=decision_summary)

    return {
        "messages": [ai_message],
        "pipeline_stages": stage_updates,
        "final_decision": final_decision,
        "final_rating": final_rating,
        "used_tokens": state.get("used_tokens", 0) + token_count,
    }


def _map_node_to_stage(node_name: str) -> str:
    mapping = {
        "Market Analyst": "market_analyst",
        "Social Analyst": "social_analyst",
        "News Analyst": "news_analyst",
        "Fundamentals Analyst": "fundamentals_analyst",
        "Bull Researcher": "bull_researcher",
        "Bear Researcher": "bear_researcher",
        "Research Manager": "research_manager",
        "Trader": "trader",
        "Aggressive Analyst": "aggressive_analyst",
        "Conservative Analyst": "conservative_analyst",
        "Neutral Analyst": "neutral_analyst",
        "Portfolio Manager": "portfolio_manager",
    }
    return mapping.get(node_name, node_name.lower().replace(" ", "_"))


def build_chat_graph() -> StateGraph:
    graph = StateGraph(ChatAgentState)

    graph.add_node("chat", chat_node)
    graph.add_node("pipeline", pipeline_node)

    graph.set_conditional_entry_point(
        route_intent,
        {"chat": "chat", "pipeline": "pipeline"},
    )

    graph.add_edge("chat", END)
    graph.add_edge("pipeline", END)

    return graph
```

- [ ] **Step 2: Create `agent.py`**

```python
import json
import logging
from datetime import date
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import HumanMessage, AIMessage

from src.agents.chat_agent.intent_router import classify_intent
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

        human_msg = HumanMessage(content=user_message)
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
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/agents/chat_agent/graph.py apps/api/src/agents/chat_agent/agent.py
git commit -m "feat(chat-agent): add graph and agent class"
```

---

### Task 3: Create DB models for chat sessions and messages

**Files:**
- Create: `apps/api/src/models/chat_session.py`
- Create: `apps/api/src/models/chat_message.py`
- Modify: `apps/api/src/models/__init__.py`

- [ ] **Step 1: Create `chat_session.py`**

```python
import uuid
from sqlalchemy import String, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class ChatSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), default="New Chat")
    updated_at = TimestampMixin.updated_at

    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    __table_args__ = (
        Index("ix_chat_sessions_user_updated", "user_id", "updated_at"),
    )
```

- [ ] **Step 2: Create `chat_message.py`**

```python
import uuid
from sqlalchemy import String, Text, ForeignKey, Integer, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from src.models.base import Base, TimestampMixin, UUIDMixin
import enum


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ChatMessage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        SQLEnum(MessageRole, name="message_role"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    stage_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped["ChatSession"] = relationship(
        "ChatSession", back_populates="messages"
    )
```

- [ ] **Step 3: Update `models/__init__.py`**

Add these lines to `apps/api/src/models/__init__.py`:

```python
from src.models.chat_session import ChatSession
from src.models.chat_message import ChatMessage
```

And add `"ChatSession"`, `"ChatMessage"` to `__all__`.

- [ ] **Step 4: Create database migration**

```bash
cd apps/api && pnpm db:revision "add chat_sessions and chat_messages tables"
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/models/ apps/api/alembic/
git commit -m "feat(chat): add ChatSession and ChatMessage models"
```

---

### Task 4: Create Pydantic schemas for chat

**Files:**
- Create: `apps/api/src/schemas/chat.py`
- Modify: `apps/api/src/schemas/__init__.py`

- [ ] **Step 1: Create `chat.py`**

```python
import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from src.schemas.base import BaseSchema, BaseReadSchema


class ChatSessionCreate(BaseSchema):
    title: str = Field(default="New Chat", max_length=255)


class ChatSessionUpdate(BaseSchema):
    title: str = Field(max_length=255)


class ChatSessionRead(BaseReadSchema):
    user_id: uuid.UUID
    title: str
    message_count: int = 0


class ChatSessionListRead(BaseSchema):
    id: uuid.UUID
    title: str
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseSchema):
    content: str = Field(min_length=1, max_length=10000)


class ChatMessageRead(BaseReadSchema):
    session_id: uuid.UUID
    role: str
    content: str
    stage_data: dict | None = None
    token_count: int | None = None


class ChatMessageListRead(BaseSchema):
    id: uuid.UUID
    role: str
    content: str
    stage_data: dict | None = None
    token_count: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ContextUsageRead(BaseSchema):
    used_tokens: int
    max_tokens: int = 128000


class SSEEvent(BaseModel):
    type: str
    data: dict | str | None = None
```

- [ ] **Step 2: Update `schemas/__init__.py`**

Add to `apps/api/src/schemas/__init__.py`:

```python
from src.schemas.chat import (
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatSessionRead,
    ChatSessionListRead,
    ChatMessageCreate,
    ChatMessageRead,
    ChatMessageListRead,
    ContextUsageRead,
    SSEEvent,
)
```

And add these names to `__all__`.

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/schemas/
git commit -m "feat(chat): add Pydantic schemas for chat sessions and messages"
```

---

### Task 5: Create ChatSessionService

**Files:**
- Create: `apps/api/src/services/chat_session.py`

- [ ] **Step 1: Create `chat_session.py`**

```python
import uuid
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.chat_session import ChatSession
from src.models.chat_message import ChatMessage
from src.core.exceptions import NotFoundException
from src.schemas.chat import (
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatSessionListRead,
)


class ChatSessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_sessions(self, user_id: uuid.UUID) -> list[ChatSessionListRead]:
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
        )
        result = await self.db.execute(stmt)
        sessions = result.scalars().all()

        session_reads = []
        for s in sessions:
            count_stmt = select(func.count()).where(
                ChatMessage.session_id == s.id
            )
            count_result = await self.db.execute(count_stmt)
            msg_count = count_result.scalar() or 0
            session_reads.append(
                ChatSessionListRead(
                    id=s.id,
                    title=s.title,
                    updated_at=s.updated_at,
                    message_count=msg_count,
                )
            )
        return session_reads

    async def create_session(
        self, user_id: uuid.UUID, payload: ChatSessionCreate
    ) -> ChatSession:
        session = ChatSession(
            user_id=user_id,
            title=payload.title,
        )
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def update_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID, payload: ChatSessionUpdate
    ) -> ChatSession:
        session = await self._get_session(session_id, user_id)
        session.title = payload.title
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def delete_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        session = await self._get_session(session_id, user_id)
        await self.db.delete(session)
        await self.db.flush()

    async def clear_context(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        session = await self._get_session(session_id, user_id)
        await self.db.execute(
            delete(ChatMessage).where(ChatMessage.session_id == session.id)
        )
        await self.db.flush()

    async def get_messages(
        self, session_id: uuid.UUID, user_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[ChatMessage]:
        session = await self._get_session(session_id, user_id)
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def add_message(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        content: str,
        stage_data: dict | None = None,
        token_count: int | None = None,
    ) -> ChatMessage:
        session = await self._get_session(session_id, user_id)
        message = ChatMessage(
            session_id=session.id,
            role=role,
            content=content,
            stage_data=stage_data,
            token_count=token_count,
        )
        self.db.add(message)
        await self.db.flush()
        await self.db.refresh(message)
        return message

    async def update_session_title(
        self, session_id: uuid.UUID, user_id: uuid.UUID, title: str
    ) -> None:
        session = await self._get_session(session_id, user_id)
        session.title = title[:255]
        await self.db.flush()

    async def _get_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> ChatSession:
        stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        if not session:
            raise NotFoundException("ChatSession", str(session_id))
        return session
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/services/chat_session.py
git commit -m "feat(chat): add ChatSessionService"
```

---

### Task 6: Create ChatAgentService (orchestration layer)

**Files:**
- Create: `apps/api/src/services/chat_agent.py`

- [ ] **Step 1: Create `chat_agent.py`**

```python
import json
import logging
import uuid
from datetime import date

from langchain_core.messages import HumanMessage

from src.agents.chat_agent.agent import ChatAgent
from src.agents.chat_agent.intent_router import classify_intent
from src.services.chat_session import ChatSessionService

logger = logging.getLogger(__name__)


class ChatAgentService:
    """Orchestrates chat agent interactions: intent routing, agent invocation,
    message persistence, and SSE event generation."""

    def __init__(self, db):
        self.session_service = ChatSessionService(db)

    async def handle_message(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        user_message: str,
        auth_token: str | None = None,
    ):
        """Process a user message and yield SSE events.

        Steps:
        1. Save user message to DB
        2. Classify intent
        3. Run chat agent and yield events
        4. Save assistant response to DB
        5. Auto-update session title if needed
        """
        await self.session_service.add_message(
            session_id, user_id, "user", user_message
        )

        intent_result = classify_intent(
            [HumanMessage(content=user_message)]
        )

        agent = ChatAgent(thread_id=str(session_id))

        accumulated_content = ""
        stage_data_list = []
        total_tokens = 0

        async for event in agent.astream_chat(user_message, intent_result):
            event_type = event.get("event", "")
            event_data = event.get("data", "")

            if event_data and isinstance(event_data, str):
                try:
                    parsed_data = json.loads(event_data)
                except json.JSONDecodeError:
                    parsed_data = {}
            else:
                parsed_data = event_data if isinstance(event_data, dict) else {}

            if event_type == "assistant_message":
                accumulated_content = parsed_data.get("content", "")
            elif event_type == "stage_update":
                stage_data_list.append(parsed_data)
            elif event_type == "context_usage":
                total_tokens = parsed_data.get("used_tokens", 0)

            yield event

        if accumulated_content:
            await self.session_service.add_message(
                session_id,
                user_id,
                "assistant",
                accumulated_content,
                stage_data=stage_data_list[-1] if stage_data_list else None,
                token_count=total_tokens,
            )

        if stage_data_list:
            last_stage = stage_data_list[-1]
            for stage in stage_data_list:
                await self.session_service.add_message(
                    session_id,
                    user_id,
                    "assistant",
                    json.dumps(stage, ensure_ascii=False),
                    stage_data=stage,
                    token_count=0,
                )

        messages = await self.session_service.get_messages(session_id, user_id, limit=2, offset=0)
        if len(messages) <= 2:
            title = user_message[:30]
            if len(user_message) > 30:
                last_space = title.rfind(" ")
                if last_space > 10:
                    title = title[:last_space]
            await self.session_service.update_session_title(
                session_id, user_id, title
            )
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/services/chat_agent.py
git commit -m "feat(chat): add ChatAgentService orchestration layer"
```

---

### Task 7: Create chat router and register dependencies

**Files:**
- Create: `apps/api/src/routers/chat.py`
- Modify: `apps/api/src/dependencies.py`
- Modify: `apps/api/src/main.py`

- [ ] **Step 1: Create `chat.py` router**

```python
import json
import uuid
from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

from src.dependencies import CurrentUser, DBSession, ChatSessionServiceDep, ChatAgentServiceDep
from src.schemas.chat import (
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatSessionRead,
    ChatSessionListRead,
    ChatMessageCreate,
    ChatMessageListRead,
    ContextUsageRead,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/sessions", response_model=list[ChatSessionListRead])
async def list_sessions(
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
):
    return await service.list_sessions(current_user.id)


@router.post("/sessions", response_model=ChatSessionRead, status_code=201)
async def create_session(
    payload: ChatSessionCreate,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
):
    session = await service.create_session(current_user.id, payload)
    return ChatSessionRead.model_validate(session)


@router.patch("/sessions/{session_id}", response_model=ChatSessionRead)
async def update_session(
    session_id: uuid.UUID,
    payload: ChatSessionUpdate,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
):
    session = await service.update_session(session_id, current_user.id, payload)
    return ChatSessionRead.model_validate(session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
):
    await service.delete_session(session_id, current_user.id)


@router.post("/sessions/{session_id}/clear-context", status_code=204)
async def clear_context(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
):
    await service.clear_context(session_id, current_user.id)

    from src.agents.chat_agent.agent import ChatAgent
    agent = ChatAgent(thread_id=str(session_id))
    agent.clear_checkpoint()


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageListRead])
async def get_messages(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    messages = await service.get_messages(session_id, current_user.id, limit, offset)
    return [ChatMessageListRead.model_validate(m) for m in messages]


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: uuid.UUID,
    payload: ChatMessageCreate,
    current_user: CurrentUser,
    agent_service: ChatAgentServiceDep,
):
    async def event_generator():
        async for event in agent_service.handle_message(
            session_id=session_id,
            user_id=current_user.id,
            user_message=payload.content,
        ):
            yield {
                "event": event.get("event", "message"),
                "data": event.get("data", "") if isinstance(event.get("data"), str) else json.dumps(event.get("data", {}), ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.get("/sessions/{session_id}/context-usage", response_model=ContextUsageRead)
async def get_context_usage(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    service: ChatSessionServiceDep,
):
    from src.agents.chat_agent.agent import ChatAgent
    agent = ChatAgent(thread_id=str(session_id))
    config = {"configurable": {"thread_id": str(session_id)}}
    state = agent.graph.get_state(config)
    used = state.values.get("used_tokens", 0) if state and state.values else 0
    return ContextUsageRead(used_tokens=used, max_tokens=128000)
```

- [ ] **Step 2: Update `dependencies.py`**

Add to `apps/api/src/dependencies.py`:

```python
from src.services.chat_session import ChatSessionService
from src.services.chat_agent import ChatAgentService

def get_chat_session_service(db: DBSession) -> ChatSessionService:
    return ChatSessionService(db)

def get_chat_agent_service(db: DBSession) -> ChatAgentService:
    return ChatAgentService(db)

ChatSessionServiceDep = Annotated[ChatSessionService, Depends(get_chat_session_service)]
ChatAgentServiceDep = Annotated[ChatAgentService, Depends(get_chat_agent_service)]
```

- [ ] **Step 3: Update `main.py`**

Add to `apps/api/src/main.py`:

```python
from src.routers import chat

# In the router registration section:
app.include_router(chat.router, prefix=settings.API_V1_PREFIX)
```

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/routers/chat.py apps/api/src/dependencies.py apps/api/src/main.py
git commit -m "feat(chat): add chat router with SSE streaming endpoints"
```

---

### Task 8: Create frontend TypeScript types

**Files:**
- Create: `apps/web/src/types/chat.ts`

- [ ] **Step 1: Create `chat.ts`**

```typescript
export type MessageRole = "user" | "assistant" | "system";

export interface ChatSession {
  id: string;
  title: string;
  updated_at: string;
  message_count: number;
}

export interface ChatSessionDetail extends ChatSession {
  user_id: string;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  stage_data?: StageData | null;
  token_count?: number | null;
  created_at: string;
}

export interface StageData {
  stage: string;
  node: string;
  progress: string;
}

export interface ContextUsage {
  used_tokens: number;
  max_tokens: number;
}

export interface SSEEvent {
  event: string;
  data: string;
}

export interface PipelineStageUpdate {
  stage: string;
  node: string;
  progress: string;
}

export interface FinalDecision {
  content: string;
  rating: string;
  ticker: string;
  trade_date: string;
}

export interface AssistantMessage {
  content: string;
  role: "assistant";
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/types/chat.ts
git commit -m "feat(chat): add frontend TypeScript types"
```

---

### Task 9: Create SSE client for chat

**Files:**
- Create: `apps/web/src/lib/chat-sse.ts`

- [ ] **Step 1: Create `chat-sse.ts`**

```typescript
import type { SSEEvent, PipelineStageUpdate, FinalDecision, AssistantMessage, ContextUsage } from "@/types/chat";

export interface SSEHandlers {
  onStageUpdate?: (data: PipelineStageUpdate) => void;
  onFinalDecision?: (data: FinalDecision) => void;
  onAssistantMessage?: (data: AssistantMessage) => void;
  onContextUsage?: (data: ContextUsage) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function streamChatMessage(
  sessionId: string,
  message: string,
  token: string,
  handlers: SSEHandlers
): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ content: message }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    handlers.onError?.(errorText || `HTTP ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    handlers.onError?.("No response body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    let currentEvent = "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const rawData = line.slice(6).trim();
        if (!rawData) continue;

        try {
          const parsed = JSON.parse(rawData);

          switch (currentEvent || parsed.event) {
            case "stage_update":
              handlers.onStageUpdate?.(parsed as PipelineStageUpdate);
              break;
            case "final_decision":
              handlers.onFinalDecision?.(parsed as FinalDecision);
              break;
            case "assistant_message":
              handlers.onAssistantMessage?.(parsed as AssistantMessage);
              break;
            case "context_usage":
              handlers.onContextUsage?.(parsed as ContextUsage);
              break;
            case "error":
              handlers.onError?.(parsed.message || "Unknown error");
              break;
            case "done":
              handlers.onDone?.();
              break;
          }
        } catch {
          // Not JSON, ignore
        }
      }
    }
  }

  handlers.onDone?.();
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/lib/chat-sse.ts
git commit -m "feat(chat): add SSE client for streaming chat messages"
```

---

### Task 10: Create frontend hooks

**Files:**
- Create: `apps/web/src/hooks/useChatSession.ts`
- Create: `apps/web/src/hooks/useChatMessages.ts`

- [ ] **Step 1: Create `useChatSession.ts`**

```typescript
"use client";

import { useState, useCallback, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";
import type { ChatSession, ChatSessionDetail } from "@/types/chat";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function useChatSession() {
  const { getToken } = useAuth();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    try {
      const token = await getToken();
      const data = await apiFetch<ChatSession[]>("/chat/sessions", {
        token: token || undefined,
      });
      setSessions(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch sessions");
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const createSession = useCallback(async (title?: string) => {
    const token = await getToken();
    const session = await apiFetch<ChatSessionDetail>("/chat/sessions", {
      token: token || undefined,
      method: "POST",
      body: JSON.stringify({ title: title || "New Chat" }),
    });
    setSessions((prev) => [session, ...prev]);
    return session;
  }, [getToken]);

  const updateSession = useCallback(async (id: string, title: string) => {
    const token = await getToken();
    const updated = await apiFetch<ChatSessionDetail>(`/chat/sessions/${id}`, {
      token: token || undefined,
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
    setSessions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, title: updated.title, updated_at: updated.updated_at } : s))
    );
  }, [getToken]);

  const deleteSession = useCallback(async (id: string) => {
    const token = await getToken();
    await apiFetch<void>(`/chat/sessions/${id}`, {
      token: token || undefined,
      method: "DELETE",
    });
    setSessions((prev) => prev.filter((s) => s.id !== id));
  }, [getToken]);

  const clearContext = useCallback(async (id: string) => {
    const token = await getToken();
    await apiFetch<void>(`/chat/sessions/${id}/clear-context`, {
      token: token || undefined,
      method: "POST",
    });
  }, [getToken]);

  return {
    sessions,
    loading,
    error,
    fetchSessions,
    createSession,
    updateSession,
    deleteSession,
    clearContext,
  };
}
```

- [ ] **Step 2: Create `useChatMessages.ts`**

```typescript
"use client";

import { useState, useCallback, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";
import { streamChatMessage } from "@/lib/chat-sse";
import type { ChatMessage, PipelineStageUpdate, ContextUsage } from "@/types/chat";

export function useChatMessages(sessionId: string | null) {
  const { getToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [stages, setStages] = useState<PipelineStageUpdate[]>([]);
  const [contextUsage, setContextUsage] = useState<ContextUsage>({ used_tokens: 0, max_tokens: 128000 });
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchMessages = useCallback(async () => {
    if (!sessionId) return;
    try {
      const token = await getToken();
      const data = await apiFetch<ChatMessage[]>(
        `/chat/sessions/${sessionId}/messages?limit=200`,
        { token: token || undefined }
      );
      setMessages(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch messages");
    }
  }, [sessionId, getToken]);

  const sendMessage = useCallback(async (content: string) => {
    if (!sessionId || isStreaming) return;

    const userMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsStreaming(true);
    setStages([]);
    setError(null);

    const token = await getToken();

    const assistantMsg: ChatMessage = {
      id: `temp-assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, assistantMsg]);

    await streamChatMessage(sessionId, content, token || "", {
      onStageUpdate: (data) => {
        setStages((prev) => [...prev, data]);
      },
      onFinalDecision: (data) => {
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
            updated[lastIdx] = {
              ...updated[lastIdx],
              content: `## Investment Decision: ${data.ticker}\n\n**Rating: ${data.rating}**\n\n${data.content}\n\n*Analysis date: ${data.trade_date}*`,
            };
          }
          return updated;
        });
      },
      onAssistantMessage: (data) => {
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
            updated[lastIdx] = {
              ...updated[lastIdx],
              content: data.content,
            };
          }
          return updated;
        });
      },
      onContextUsage: (data) => {
        setContextUsage(data);
      },
      onError: (msg) => {
        setError(msg);
      },
      onDone: () => {
        setIsStreaming(false);
        fetchMessages();
      },
    });
  }, [sessionId, isStreaming, getToken, fetchMessages]);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
  }, []);

  return {
    messages,
    isStreaming,
    stages,
    contextUsage,
    error,
    fetchMessages,
    sendMessage,
    stopStreaming,
  };
}
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/hooks/useChatSession.ts apps/web/src/hooks/useChatMessages.ts
git commit -m "feat(chat): add frontend hooks for session and message management"
```

---

### Task 11: Create core frontend chat components (ChatLayout, SessionSidebar, ChatArea)

**Files:**
- Create: `apps/web/src/components/chat/ChatLayout.tsx`
- Create: `apps/web/src/components/chat/SessionSidebar.tsx`
- Create: `apps/web/src/components/chat/SessionItem.tsx`
- Create: `apps/web/src/components/chat/NewSessionButton.tsx`

- [ ] **Step 1: Create `NewSessionButton.tsx`**

```tsx
"use client";

import { Plus } from "lucide-react";

interface NewSessionButtonProps {
  onClick: () => void;
  disabled?: boolean;
}

export function NewSessionButton({ onClick, disabled }: NewSessionButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg
        bg-terracotta text-white font-medium text-sm
        hover:bg-terracotta/90 transition-colors
        disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <Plus className="w-4 h-4" />
      New Chat
    </button>
  );
}
```

- [ ] **Step 2: Create `SessionItem.tsx`**

```tsx
"use client";

import { Trash2, Pencil } from "lucide-react";
import { useState } from "react";
import type { ChatSession } from "@/types/chat";

interface SessionItemProps {
  session: ChatSession;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
}

export function SessionItem({ session, isActive, onSelect, onDelete, onRename }: SessionItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(session.title);

  const handleSubmitRename = () => {
    if (editTitle.trim() && editTitle !== session.title) {
      onRename(session.id, editTitle.trim());
    }
    setIsEditing(false);
  };

  return (
    <div
      onClick={() => onSelect(session.id)}
      className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors
        ${isActive ? "bg-terracotta/10 text-terracotta" : "hover:bg-warm-gray/10 text-ink"}`}
    >
      {isEditing ? (
        <input
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onBlur={handleSubmitRename}
          onKeyDown={(e) => e.key === "Enter" && handleSubmitRename()}
          className="flex-1 text-sm bg-white border border-divider rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-terracotta"
          autoFocus
        />
      ) : (
        <span className="flex-1 text-sm truncate" onDoubleClick={() => setIsEditing(true)}>
          {session.title}
        </span>
      )}
      <div className="hidden group-hover:flex items-center gap-1">
        <button
          onClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
          className="p-1 rounded hover:bg-warm-gray/20"
        >
          <Pencil className="w-3 h-3" />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(session.id); }}
          className="p-1 rounded hover:bg-red-100 text-red-500"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
      <span className="text-xs text-warm-gray/70">
        {new Date(session.updated_at).toLocaleDateString()}
      </span>
    </div>
  );
}
```

- [ ] **Step 3: Create `SessionSidebar.tsx`**

```tsx
"use client";

import { useChatSession } from "@/hooks/useChatSession";
import { SessionItem } from "./SessionItem";
import { NewSessionButton } from "./NewSessionButton";
import type { ChatSession } from "@/types/chat";

interface SessionSidebarProps {
  activeSessionId: string | null;
  onSessionSelect: (session: ChatSession) => void;
}

export function SessionSidebar({ activeSessionId, onSessionSelect }: SessionSidebarProps) {
  const { sessions, loading, createSession, deleteSession, updateSession } = useChatSession();

  const handleNewSession = async () => {
    const session = await createSession();
    if (session) {
      onSessionSelect(session as unknown as ChatSession);
    }
  };

  return (
    <div className="w-64 h-full bg-cream border-r border-divider flex flex-col">
      <div className="p-3">
        <NewSessionButton onClick={handleNewSession} disabled={loading} />
      </div>
      <div className="flex-1 overflow-y-auto px-2">
        {sessions.map((session) => (
          <SessionItem
            key={session.id}
            session={session}
            isActive={session.id === activeSessionId}
            onSelect={(id) => {
              const s = sessions.find((s) => s.id === id);
              if (s) onSessionSelect(s);
            }}
            onDelete={deleteSession}
            onRename={updateSession}
          />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create `ChatLayout.tsx`**

```tsx
"use client";

import { useState } from "react";
import { SessionSidebar } from "./SessionSidebar";
import { ChatArea } from "./ChatArea";
import type { ChatSession } from "@/types/chat";

export function ChatLayout() {
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);

  return (
    <div className="flex h-[calc(100vh-4rem)] bg-cream">
      <SessionSidebar
        activeSessionId={activeSession?.id ?? null}
        onSessionSelect={setActiveSession}
      />
      <div className="flex-1">
        {activeSession ? (
          <ChatArea sessionId={activeSession.id} />
        ) : (
          <div className="flex items-center justify-center h-full text-warm-gray">
            <p className="text-lg">Select a session or create a new one to start chatting</p>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/chat/
git commit -m "feat(chat): add ChatLayout, SessionSidebar, SessionItem, NewSessionButton"
```

---

### Task 12: Create chat UI components (ChatArea, MessageList, MessageBubble, PipelineProgress, ContextGauge, ChatInput)

**Files:**
- Create: `apps/web/src/components/chat/ChatArea.tsx`
- Create: `apps/web/src/components/chat/MessageList.tsx`
- Create: `apps/web/src/components/chat/MessageBubble.tsx`
- Create: `apps/web/src/components/chat/PipelineProgress.tsx`
- Create: `apps/web/src/components/chat/ContextGauge.tsx`
- Create: `apps/web/src/components/chat/ChatInput.tsx`

- [ ] **Step 1: Create `MessageBubble.tsx`**

```tsx
"use client";

import type { ChatMessage } from "@/types/chat";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed
          ${isUser
            ? "bg-terracotta text-white rounded-br-sm"
            : "bg-ink/5 text-ink rounded-bl-sm"
          }`}
      >
        <div className="whitespace-pre-wrap prose prose-sm max-w-none">
          {message.content}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `PipelineProgress.tsx`**

```tsx
"use client";

import type { PipelineStageUpdate } from "@/types/chat";

const STAGE_LIST: Record<string, string> = {
  market_analyst: "Market Analyst",
  social_analyst: "Social Analyst",
  news_analyst: "News Analyst",
  fundamentals_analyst: "Fundamentals",
  bull_researcher: "Bull Researcher",
  bear_researcher: "Bear Researcher",
  research_manager: "Research Manager",
  trader: "Trader",
  aggressive_analyst: "Risk Aggressive",
  conservative_analyst: "Risk Conservative",
  neutral_analyst: "Risk Neutral",
  portfolio_manager: "Portfolio Manager",
};

interface PipelineProgressProps {
  stages: PipelineStageUpdate[];
}

export function PipelineProgress({ stages }: PipelineProgressProps) {
  if (stages.length === 0) return null;

  const stageNames = Object.keys(STAGE_LIST);

  return (
    <div className="mb-4 p-3 bg-ink/5 rounded-xl">
      <p className="text-xs font-medium text-warm-gray mb-2">
        Pipeline Progress ({stages.length}/{stageNames.length})
      </p>
      <div className="flex flex-wrap gap-1.5">
        {stageNames.map((stage, idx) => {
          const completed = stages.some((s) => s.stage === stage);
          const isCurrent = !completed && stages.length === idx;
          return (
            <div
              key={stage}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors
                ${completed
                  ? "bg-sage-muted/30 text-sage-muted"
                  : isCurrent
                    ? "bg-terracotta/20 text-terracotta animate-pulse"
                    : "bg-warm-gray/10 text-warm-gray"
                }`}
            >
              {STAGE_LIST[stage]}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create `ContextGauge.tsx`**

```tsx
"use client";

import type { ContextUsage } from "@/types/chat";

interface ContextGaugeProps {
  usage: ContextUsage;
}

export function ContextGauge({ usage }: ContextGaugeProps) {
  const pct = Math.min(100, Math.round((usage.used_tokens / usage.max_tokens) * 100));

  const barColor =
    pct > 85 ? "bg-red-500" :
    pct > 60 ? "bg-yellow-500" :
    "bg-sage-muted";

  return (
    <div className="flex items-center gap-2 text-xs text-warm-gray px-2 py-1">
      <span>Context</span>
      <div className="flex-1 h-2 bg-warm-gray/20 rounded-full overflow-hidden max-w-32">
        <div
          className={`h-full ${barColor} rounded-full transition-all duration-300`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span>{pct}%</span>
      {pct > 85 && (
        <span className="text-red-500 font-medium animate-pulse">!</span>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Create `ChatInput.tsx`**

```tsx
"use client";

import { useState } from "react";
import { Send, Square } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string) => void;
  isStreaming: boolean;
  onStop?: () => void;
}

export function ChatInput({ onSend, isStreaming, onStop }: ChatInputProps) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setInput("");
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2 p-3 border-t border-divider bg-cream">
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Ask about a stock or market analysis..."
        disabled={isStreaming}
        className="flex-1 rounded-lg border border-divider bg-white px-4 py-2.5 text-sm
          focus:outline-none focus:ring-2 focus:ring-terracotta/30
          disabled:opacity-50 disabled:cursor-not-allowed"
      />
      {isStreaming ? (
        <button
          type="button"
          onClick={onStop}
          className="p-2.5 rounded-lg bg-red-100 text-red-600 hover:bg-red-200 transition-colors"
        >
          <Square className="w-4 h-4" />
        </button>
      ) : (
        <button
          type="submit"
          disabled={!input.trim()}
          className="p-2.5 rounded-lg bg-terracotta text-white hover:bg-terracotta/90 transition-colors
            disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="w-4 h-4" />
        </button>
      )}
    </form>
  );
}
```

- [ ] **Step 5: Create `MessageList.tsx`**

```tsx
"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/types/chat";
import { MessageBubble } from "./MessageBubble";
import { PipelineProgress } from "./PipelineProgress";
import type { PipelineStageUpdate } from "@/types/chat";

interface MessageListProps {
  messages: ChatMessage[];
  stages: PipelineStageUpdate[];
  isStreaming: boolean;
}

export function MessageList({ messages, stages, isStreaming }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevMsgCount = useRef(0);

  useEffect(() => {
    if (messages.length > prevMsgCount.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
    prevMsgCount.current = messages.length;
  }, [messages.length]);

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto p-4">
      {stages.length > 0 && isStreaming && (
        <PipelineProgress stages={stages} />
      )}
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isStreaming && messages.length > 0 && messages[messages.length - 1].role === "user" && (
        <div className="flex justify-start mb-4">
          <div className="bg-ink/5 rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm text-ink/60 animate-pulse">
            Thinking...
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
```

- [ ] **Step 6: Create `ChatArea.tsx`**

```tsx
"use client";

import { useEffect } from "react";
import { useChatMessages } from "@/hooks/useChatMessages";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { ContextGauge } from "./ContextGauge";
import { Trash2, RotateCcw } from "lucide-react";
import { useChatSession } from "@/hooks/useChatSession";

interface ChatAreaProps {
  sessionId: string;
}

export function ChatArea({ sessionId }: ChatAreaProps) {
  const { messages, isStreaming, stages, contextUsage, error, fetchMessages, sendMessage, stopStreaming } =
    useChatMessages(sessionId);
  const { clearContext, deleteSession } = useChatSession();

  useEffect(() => {
    fetchMessages();
  }, [sessionId, fetchMessages]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b border-divider bg-cream">
        <ContextGauge usage={contextUsage} />
        <div className="flex items-center gap-2">
          <button
            onClick={async () => {
              await clearContext(sessionId);
              await fetchMessages();
            }}
            className="p-1.5 rounded hover:bg-warm-gray/10 text-warm-gray"
            title="Clear context"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
      </div>
      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-700 text-sm">{error}</div>
      )}
      <MessageList messages={messages} stages={stages} isStreaming={isStreaming} />
      <ChatInput onSend={sendMessage} isStreaming={isStreaming} onStop={stopStreaming} />
    </div>
  );
}
```

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/components/chat/
git commit -m "feat(chat): add ChatArea, MessageList, MessageBubble, PipelineProgress, ContextGauge, ChatInput"
```

---

### Task 13: Create chat page route and update navigation

**Files:**
- Create: `apps/web/src/app/[locale]/recommendations/chat/page.tsx`
- Modify: `apps/web/src/app/[locale]/recommendations/layout.tsx`

- [ ] **Step 1: Create chat page**

```tsx
import type { Metadata } from "next";
import { ChatLayout } from "@/components/chat/ChatLayout";

export const metadata: Metadata = {
  title: "AI Chat - AlphaDesk",
  description: "Chat with the AlphaDesk AI investment analyst",
};

export default function ChatPage() {
  return <ChatLayout />;
}
```

- [ ] **Step 2: Add "Chat" nav item to layout.tsx**

In `apps/web/src/app/[locale]/recommendations/layout.tsx`, add a "Chat" entry to the `navItems` array:

```typescript
import { MessageCircle } from "lucide-react";

// In navItems array, add:
{ icon: MessageCircle, href: "/recommendations/chat", labelKey: "chat" },
```

Also add the translation key. Check the i18n messages file (likely in `messages/` or `public/locales/`) and add `"chat": "Chat"` / `"chat": "AI 对话"` for English and Chinese locales respectively.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/ apps/web/src/components/chat/ apps/web/messages/
git commit -m "feat(chat): add chat page route and navigation entry"
```

---

### Task 14: Run lint and build validation

- [ ] **Step 1: Run backend lint**

```bash
cd apps/api && pnpm lint
```

Expected: No errors.

- [ ] **Step 2: Run frontend lint**

```bash
cd apps/web && pnpm lint
```

Expected: No errors.

- [ ] **Step 3: Run frontend build**

```bash
cd apps/web && pnpm build
```

Expected: Build completes successfully.

- [ ] **Step 4: Start backend and test endpoints manually**

```bash
cd apps/api && pnpm dev
```

Test these endpoints:
1. `POST /api/v1/chat/sessions` — create session
2. `GET /api/v1/chat/sessions` — list sessions
3. `POST /api/v1/chat/sessions/{id}/messages` — send message (SSE)
4. `GET /api/v1/chat/sessions/{id}/messages` — get message history
5. `GET /api/v1/chat/sessions/{id}/context-usage` — get token usage

- [ ] **Step 5: Commit any fixes**

If lint or build revealed issues, fix them and commit:

```bash
git add -A && git commit -m "fix(chat): resolve lint and build issues"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - Session CRUD: Task 5 (service) + Task 7 (router) ✅
   - Message persistence: Task 6 (ChatAgentService) ✅
   - SSE streaming: Task 7 (router) + Task 9 (frontend SSE) ✅
   - Pipeline progress: Task 2 (graph.py pipeline_node) + Task 12 (PipelineProgress.tsx) ✅
   - Context gauge: Task 2 (used_tokens in state) + Task 12 (ContextGauge.tsx) ✅
   - Clear context: Task 5 (service) + Task 7 (router) ✅
   - Auto title: Task 6 (ChatAgentService.handle_message) ✅
   - Intent routing: Task 1 (intent_router.py) ✅

2. **Placeholder scan:** No TBD, TODO, or placeholder steps. All code is complete.

3. **Type consistency:**
   - `ChatAgentState` fields match across `state.py`, `graph.py`, `agent.py` ✅
   - `ChatSession` / `ChatMessage` models match schemas ✅
   - SSE event types match between `chat.py` router and `chat-sse.ts` ✅
   - TypeScript types match what the API returns ✅

4. **Potential issues to watch during implementation:**
   - LangGraph `SqliteSaver` uses synchronous SQLite — may need async wrapper or `aiosqlite` for `MemorySaver`
   - The `pipeline_node` in `graph.py` uses `asyncio.run()` which won't work inside an already-running event loop — needs refactoring to use `await` directly or `asyncio.create_task()`
   - The `handle_message` method in `ChatAgentService` saves pipeline stages as separate messages, which may create duplicates with the final decision message — needs cleanup during implementation
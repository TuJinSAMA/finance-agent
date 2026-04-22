# Chat Agent Design Spec

**Date:** 2026-04-22  
**Status:** Approved  
**Related Plan:** `docs/superpowers/plans/2026-04-22-decision-chain-migration.md`

---

## Overview

Add a dedicated chat page (`/[locale]/recommendations/chat`) where users can converse with the Decision Chain Agent. The Agent responds conversationally for general questions and automatically triggers the multi-stage pipeline when the user asks for stock analysis. Each conversation is a **session** with its own title, persistent history, and clearable context. The UI shows pipeline stage progress and context window utilization.

---

## Requirements

1. **Session-based conversations** — each session has a title, persistent messages, and independent context
2. **Auto context carry** — new messages automatically include conversation history for topic relevance
3. **Clear context** — per-session context clearing that removes LangGraph checkpoint + DB messages while keeping the session record
4. **Pipeline as a tool** — when intent is stock analysis, the full 12-stage pipeline runs automatically; otherwise normal chat
5. **Stage progress** — pipeline execution shows a step indicator (1/12 → 2/12 → ... → 12/12)
6. **Context gauge** — visual progress bar showing context window remaining capacity
7. **Sidebar** — left sidebar for session management (list, create, delete, rename)

---

## Architecture Choice: LangGraph Checkpoint

**Decision:** Use LangGraph's `MemorySaver` (SQLite-backed) to manage conversation state. A lightweight DB layer stores session metadata and messages for the frontend.

**Rationale:**
- LangGraph natively manages checkpoint state per thread, including tool call intermediates
- Switching sessions = switching thread IDs
- Avoids duplicating context window management logic
- Token counting comes from LLM `usage_metadata`, no need for a separate estimator

---

## Data Model

### `chat_sessions`

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Also used as LangGraph `thread_id` |
| user_id | UUID (FK → users) | Owner |
| title | VARCHAR(255) | Default "New Chat", auto-set from first reply |
| created_at | TIMESTAMP | Server default `now()` |
| updated_at | TIMESTAMP | Auto-updated on message |

### `chat_messages`

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| session_id | UUID (FK → chat_sessions) | |
| role | ENUM('user', 'assistant', 'system') | |
| content | TEXT | Message body |
| stage_data | JSONB (nullable) | Pipeline stage info: `{stage, node, progress}` |
| token_count | INTEGER (nullable) | Tokens consumed by this message |
| created_at | TIMESTAMP | |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/chat/sessions` | List user's sessions (sorted by `updated_at` desc) |
| POST | `/api/v1/chat/sessions` | Create session, returns `{id, title}` |
| PATCH | `/api/v1/chat/sessions/{id}` | Update title |
| DELETE | `/api/v1/chat/sessions/{id}` | Delete session + messages + LangGraph checkpoint |
| POST | `/api/v1/chat/sessions/{id}/clear-context` | Clear messages and checkpoint, keep session |
| GET | `/api/v1/chat/sessions/{id}/messages` | Paginated message list |
| POST | `/api/v1/chat/sessions/{id}/messages` | Send message, returns SSE stream |
| GET | `/api/v1/chat/sessions/{id}/context-usage` | Get `{used_tokens, max_tokens}` |

### SSE Event Protocol (for `POST .../messages`)

```typescript
// Streaming text token
{ type: "token", content: "..." }

// Pipeline stage progress
{ type: "stage_update", stage: "market_analyst", node: "Market Analyst", progress: "1/12" }

// Pipeline final decision
{ type: "final_decision", content: "...", rating: "BUY", ticker: "600519" }

// Context window usage update
{ type: "context_usage", used_tokens: 12345, max_tokens: 128000 }

// Error
{ type: "error", message: "..." }

// Stream complete
{ type: "done" }
```

---

## Core Agent Logic

### ChatAgent (new class)

Wraps the existing `TradingDecisionChain` with an intent router and chat capability.

```python
# apps/api/src/agents/chat_agent/
#   __init__.py
#   agent.py          # ChatAgent class
#   intent_router.py   # Intent classification
#   graph.py           # LangGraph state graph for routing
```

**LangGraph structure:**

```
Entry → intent_router
              │
              ├── "pipeline" → pipeline_node → format_pipeline_result → END
              │
              └── "chat" → chat_node → END
```

### Intent Router

A lightweight LLM call using `quick_think_llm` that classifies user intent:

- **"pipeline"** — user asks to analyze a stock, requests investment advice, mentions a ticker symbol
- **"chat"** — everything else: greetings, follow-up questions, general knowledge

The router receives the last 3 messages as context to handle follow-ups like "tell me more" which should route to "chat" (since pipeline results already exist in context).

### Pipeline Node

Invokes `TradingDecisionChain` with SSE event mapping. Each `stage_update` from the existing pipeline is forwarded to the client. The `final_decision` is formatted and returned.

### Chat Node

Simple LLM call using `quick_think_llm` with the conversation history. For general Q&A about stocks, markets, or follow-up discussion about pipeline results.

### Context Management

- **Checkpoint:** LangGraph `MemorySaver` with `thread_id = session.id`
- **Clear context:** `POST .../clear-context` deletes all checkpoints for the thread and all messages in DB
- **Token counting:** Extract from `usage_metadata` in LLM response; accumulate per-message and send `context_usage` events

### Auto Title

When a session receives its first assistant reply, the title is auto-generated from the first 30 characters of the response (truncated at word boundary). User can always rename.

---

## Frontend

### Route

```
/[locale]/recommendations/chat  →  ChatPage
```

Nested under the existing `recommendations` layout (sidebar + topbar). Add a "Chat" nav item to both desktop sidebar and mobile bottom nav.

### Component Tree

```
ChatPage
├── ChatLayout
│   ├── SessionSidebar
│   │   ├── NewSessionButton
│   │   └── SessionItem (×N)
│   │       ├── title (editable on double-click)
│   │       ├── timestamp
│   │       └── delete button
│   └── ChatArea
│       ├── MessageList
│       │   ├── MessageBubble (user)
│       │   ├── MessageBubble (assistant, with markdown rendering)
│       │   └── PipelineProgress (shown during pipeline execution)
│       ├── ContextGauge (progress bar at bottom of message area)
│       └── ChatInput (text input + send button, disabled during response)
```

### Key Interactions

**New session:** Click "New Chat" → `POST /sessions` → sidebar adds item → right side shows empty chat

**Send message:** Type in `ChatInput` → `POST /sessions/{id}/messages` → SSE stream connects → tokens render progressively → `MessageBubble` updates in real-time

**Pipeline execution:** When `stage_update` events arrive, `PipelineProgress` shows steps (1/12, 2/12, etc.). When `final_decision` arrives, it renders as a formatted decision card.

**Clear context:** Session menu → "Clear Context" → `POST .../clear-context` → messages disappear, session stays

**Context gauge:** `ContextGauge` polls `GET .../context-usage` periodically (every 30s or on each message). Shows color-coded progress bar:
- Green: 0-60% used
- Yellow: 60-85% used  
- Red: 85-100% used

When > 85%, show a warning tooltip.

**Auto-scroll:** Message list auto-scrolls to bottom on new messages; user scroll up pauses auto-scroll, scroll-to-bottom button appears.

### Mobile

- Sidebar hidden by default, hamburger menu toggles it
- Chat takes full width
- Bottom nav adds "Chat" tab

---

## Error Handling

| Scenario | Behavior |
|---|---|
| LLM API failure | SSE `error` event, frontend shows error toast, session remains usable |
| Pipeline stage failure | SSE `stage_error`, skip remaining stages, show partial results + error |
| Context exceeds 85% | `context_warning` event, frontend shows warning banner |
| Context exceeds 95% | Auto-truncate oldest messages, inform user |
| Unauthenticated | Middleware redirects to login |
| Concurrent messages | Disable input during response, prevent double-submit |

---

## File Structure (New Files)

### Backend

```
apps/api/src/
├── models/
│   ├── chat_session.py          # ChatSession model
│   ├── chat_message.py           # ChatMessage model
│   └── __init__.py               # Update re-exports
├── schemas/
│   ├── chat.py                   # ChatSession + ChatMessage schemas
│   └── __init__.py               # Update re-exports
├── services/
│   ├── chat_session.py           # ChatSessionService
│   └── chat_agent.py             # ChatAgentService (wraps ChatAgent)
├── agents/chat_agent/
│   ├── __init__.py               # Exports ChatAgent
│   ├── agent.py                  # ChatAgent class
│   ├── intent_router.py          # Intent classification
│   ├── graph.py                  # LangGraph state + routing
│   └── state.py                  # ChatAgentState TypedDict
├── routers/
│   └── chat.py                   # FastAPI router with all endpoints
└── dependencies.py               # Add chat service dependencies
```

### Frontend

```
apps/web/src/
├── app/[locale]/recommendations/chat/
│   └── page.tsx                  # Chat page entry
├── components/chat/
│   ├── ChatLayout.tsx
│   ├── SessionSidebar.tsx
│   ├── SessionItem.tsx
│   ├── ChatArea.tsx
│   ├── MessageList.tsx
│   ├── MessageBubble.tsx
│   ├── PipelineProgress.tsx
│   ├── ContextGauge.tsx
│   ├── ChatInput.tsx
│   └── NewSessionButton.tsx
├── hooks/
│   ├── useChatSession.ts         # Session CRUD + list
│   └── useChatMessages.ts        # Message sending + SSE stream
└── lib/
    └── chat-sse.ts               # SSE client for chat streaming
```

---

## Database Migration

One Alembic migration:

```bash
cd apps/api && pnpm db:revision "add chat_sessions and chat_messages tables"
```

Creating `chat_sessions` and `chat_messages` tables with appropriate indexes:
- `ix_chat_sessions_user_id` on `chat_sessions.user_id`
- `ix_chat_messages_session_id` on `chat_messages.session_id`
- `ix_chat_sessions_updated_at` on `chat_sessions.updated_at` (for sorting)

---

## Security

- All chat endpoints require Clerk authentication (reuse existing `get_current_user` dependency)
- Users can only access their own sessions (filter by `user_id`)
- No raw API keys exposed to frontend
- Rate limiting on `POST .../messages` to prevent abuse (consider FastAPI middleware)

---

## Open Questions / Future Enhancements

1. **Conversation search** — search across session messages (not in MVP)
2. **Export conversation** — download as PDF/Markdown (not in MVP)
3. **Multiple model selection** — let user choose between deep_think and quick_think (not in MVP)
4. **Streaming markdown rendering** — render markdown progressively as tokens arrive (should include in initial implementation)
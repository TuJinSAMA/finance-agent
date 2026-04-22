import json
import uuid

from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

from src.dependencies import CurrentUser, ChatSessionServiceDep, ChatAgentServiceDep
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
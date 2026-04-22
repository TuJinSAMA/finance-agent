import json
import logging
import uuid

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

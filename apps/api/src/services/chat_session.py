import uuid
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

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
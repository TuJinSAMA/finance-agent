import logging

from fastapi import APIRouter, Request, Response
from svix.webhooks import Webhook, WebhookVerificationError

from src.core.config import settings
from src.core.database import async_session
from src.schemas.user import UserCreate, UserUpdate
from src.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _extract_user_create(data: dict) -> UserCreate:
    """Extract UserCreate fields from Clerk webhook user data."""
    email = None
    email_addresses = data.get("email_addresses", [])
    primary_email_id = data.get("primary_email_address_id")
    for addr in email_addresses:
        if addr.get("id") == primary_email_id:
            email = addr.get("email_address") or None
            break
    if not email and email_addresses:
        email = email_addresses[0].get("email_address") or None

    return UserCreate(
        clerk_id=data["id"],
        email=email,
        username=data.get("username"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        avatar_url=data.get("image_url"),
    )


def _extract_user_update(data: dict) -> UserUpdate:
    """Extract UserUpdate fields from Clerk webhook user data."""
    email = None
    email_addresses = data.get("email_addresses", [])
    primary_email_id = data.get("primary_email_address_id")
    for addr in email_addresses:
        if addr.get("id") == primary_email_id:
            email = addr.get("email_address")
            break

    return UserUpdate(
        email=email,
        username=data.get("username"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        avatar_url=data.get("image_url"),
    )


@router.post("/clerk")
async def clerk_webhook(request: Request):
    body = await request.body()
    headers = dict(request.headers)

    try:
        wh = Webhook(settings.CLERK_WEBHOOK_SIGNING_SECRET)
        evt = wh.verify(body, headers)
    except WebhookVerificationError:
        logger.warning("Clerk webhook signature verification failed")
        return Response(status_code=400, content="Invalid signature")

    event_type: str = evt.get("type", "")
    data: dict = evt.get("data", {})
    clerk_id: str = data.get("id", "")

    logger.info("Clerk webhook received: type=%s clerk_id=%s", event_type, clerk_id)

    async with async_session() as session:
        service = UserService(session)
        try:
            if event_type == "user.created":
                payload = _extract_user_create(data)
                await service.upsert_by_clerk_id(payload)
                logger.info("User synced (created): %s", clerk_id)

            elif event_type == "user.updated":
                existing = await service.get_by_clerk_id(clerk_id)
                if existing:
                    payload = _extract_user_update(data)
                    await service.update_by_clerk_id(clerk_id, payload)
                    logger.info("User synced (updated): %s", clerk_id)
                else:
                    payload = _extract_user_create(data)
                    await service.upsert_by_clerk_id(payload)
                    logger.info("User synced (created via update): %s", clerk_id)

            elif event_type == "user.deleted":
                await service.soft_delete_by_clerk_id(clerk_id)
                logger.info("User synced (soft-deleted): %s", clerk_id)

            else:
                logger.debug("Unhandled Clerk event type: %s", event_type)

            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Failed to process Clerk webhook: %s", event_type)
            return Response(status_code=500, content="Internal error")

    return Response(status_code=200, content="ok")

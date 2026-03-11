"""
Clerk JWT authentication for FastAPI.

Verifies Bearer tokens from the Authorization header against Clerk's JWKS,
then resolves the clerk_id (JWT `sub` claim) to a local User record.
"""

import logging
import time

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.models.user import User
from src.services.user import UserService

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer()

_jwks_cache: dict = {"keys": [], "fetched_at": 0.0}
_JWKS_CACHE_TTL = 3600  # 1 hour


async def _get_jwks() -> list[dict]:
    """Fetch and cache Clerk JWKS public keys."""
    now = time.time()
    if _jwks_cache["keys"] and now - _jwks_cache["fetched_at"] < _JWKS_CACHE_TTL:
        return _jwks_cache["keys"]

    url = settings.CLERK_JWKS_URL
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            _jwks_cache["keys"] = data.get("keys", [])
            _jwks_cache["fetched_at"] = now
            logger.info("Fetched Clerk JWKS (%d keys)", len(_jwks_cache["keys"]))
            return _jwks_cache["keys"]
    except Exception:
        logger.exception("Failed to fetch Clerk JWKS from %s", url)
        if _jwks_cache["keys"]:
            return _jwks_cache["keys"]
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )


def _decode_token(token: str, jwks: list[dict]) -> dict:
    """Decode and verify a Clerk JWT using the JWKS public keys."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    kid = header.get("kid")
    key_data = next((k for k in jwks if k.get("kid") == kid), None)
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signing key not found",
        )

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
    try:
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: extract and verify Clerk JWT, return local User."""
    jwks = await _get_jwks()
    payload = _decode_token(credentials.credentials, jwks)

    clerk_id = payload.get("sub")
    if not clerk_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )

    service = UserService(db)
    user = await service.get_by_clerk_id(clerk_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user

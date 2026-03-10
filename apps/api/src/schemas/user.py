from pydantic import EmailStr

from src.schemas.base import BaseReadSchema, BaseSchema


class UserCreate(BaseSchema):
    clerk_id: str
    email: EmailStr | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None


class UserUpdate(BaseSchema):
    email: EmailStr | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    is_active: bool | None = None


class UserRead(BaseReadSchema):
    clerk_id: str
    email: str | None
    username: str | None
    first_name: str | None
    last_name: str | None
    avatar_url: str | None
    is_active: bool

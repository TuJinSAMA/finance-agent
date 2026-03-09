from pydantic import EmailStr

from src.schemas.base import BaseReadSchema, BaseSchema


class UserCreate(BaseSchema):
    username: str
    email: EmailStr


class UserUpdate(BaseSchema):
    username: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None


class UserRead(BaseReadSchema):
    username: str
    email: str
    is_active: bool

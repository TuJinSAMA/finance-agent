import uuid

from fastapi import APIRouter

from src.dependencies import UserServiceDep
from src.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
async def list_users(service: UserServiceDep):
    return await service.list()


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: uuid.UUID, service: UserServiceDep):
    return await service.get_by_id(user_id)


@router.post("", response_model=UserRead, status_code=201)
async def create_user(payload: UserCreate, service: UserServiceDep):
    return await service.create(payload)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID, payload: UserUpdate, service: UserServiceDep
):
    return await service.update(user_id, payload)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: uuid.UUID, service: UserServiceDep):
    await service.delete(user_id)

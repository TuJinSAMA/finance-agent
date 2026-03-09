import uuid
from datetime import datetime

from pydantic import BaseModel


class BaseSchema(BaseModel):
    model_config = {"from_attributes": True}


class BaseReadSchema(BaseSchema):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

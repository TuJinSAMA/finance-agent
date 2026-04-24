from datetime import datetime

from pydantic import BaseModel


class GeoEventRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    source_name: str
    source_url: str
    title: str
    summary: str
    impact_level: int
    categories: str | None
    region: str | None
    event_date: datetime
    is_active: bool


class GeoEventListResponse(BaseModel):
    events: list[GeoEventRead]
    total: int
    level3_count: int
    level2_count: int
    last_updated: datetime | None


class GeoEventQueryParams(BaseModel):
    impact_level: int | None = None
    category: str | None = None
    region: str | None = None
    limit: int = 20
    offset: int = 0
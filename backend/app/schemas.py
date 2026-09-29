from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SampleOut(BaseModel):
    t_s: float
    bean_temp_c: float
    env_temp_c: float
    quality: str


class EventIn(BaseModel):
    event_type: str = Field(pattern="^(charge|turn|first_crack|drop|damper|marker)$")
    event_time: float = Field(ge=0)
    value: float | None = None
    operator: str = ""
    note: str = ""

    @field_validator("operator")
    @classmethod
    def operator_required_for_manual(cls, v):
        return v


class EventOut(BaseModel):
    id: int
    event_type: str
    event_time: float
    value: float | None
    source: str
    operator: str
    note: str
    method: dict | None
    supersedes_id: int | None
    is_current: bool
    created_at: datetime


class BatchSummary(BaseModel):
    id: int
    code: str
    profile_name: str
    bean_origin: str
    roast_date: str
    n_samples: int
    n_gaps: int


class TurnSuggestionOut(BaseModel):
    t_s: float
    bean_temp_c: float
    method: dict

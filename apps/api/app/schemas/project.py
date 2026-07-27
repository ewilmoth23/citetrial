from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.entities import ProjectStatus
from app.schemas.common import ORMModel


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    primary_question: str = Field(min_length=3, max_length=5000)
    description: str | None = Field(default=None, max_length=20_000)

    @field_validator("title", "primary_question")
    @classmethod
    def strip_required(cls, value: str) -> str:
        if not (cleaned := value.strip()):
            raise ValueError("must not be blank")
        return cleaned


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    primary_question: str | None = Field(default=None, min_length=3, max_length=5000)
    description: str | None = Field(default=None, max_length=20_000)

    @field_validator("title", "primary_question")
    @classmethod
    def strip_optional_required(cls, value: str | None) -> str | None:
        if value is not None and not (cleaned := value.strip()):
            raise ValueError("must not be blank")
        return cleaned if value is not None else None


class ProjectRead(ORMModel):
    id: str
    title: str
    primary_question: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    source_count: int = 0
    processed_source_count: int = 0
    claim_count: int = 0
    disputed_claim_count: int = 0
    unresolved_claim_count: int = 0
    timeline_event_count: int = 0
    brief_status: str | None = None


class ActivityRead(ORMModel):
    id: str
    action: str
    detail: str | None
    created_at: datetime

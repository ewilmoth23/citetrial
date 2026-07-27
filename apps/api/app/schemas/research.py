from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel
from app.schemas.source import SearchResult


class ClaimCreate(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    claim_type: str = Field(
        default="factual",
        pattern="^(factual|causal|interpretive|comparative|chronological|unresolved_question)$",
    )
    status: str = Field(
        default="proposed",
        pattern="^(proposed|supported|partially_supported|disputed|contradicted|insufficient_evidence|resolved|archived)$",
    )
    confidence: float | None = Field(default=None, ge=0, le=1)
    user_notes: str | None = Field(default=None, max_length=20_000)


class ClaimUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=10_000)
    claim_type: str | None = Field(
        default=None,
        pattern="^(factual|causal|interpretive|comparative|chronological|unresolved_question)$",
    )
    status: str | None = Field(
        default=None,
        pattern="^(proposed|supported|partially_supported|disputed|contradicted|insufficient_evidence|resolved|archived)$",
    )
    confidence: float | None = Field(default=None, ge=0, le=1)
    user_notes: str | None = Field(default=None, max_length=20_000)


class EvidenceCreate(BaseModel):
    source_id: str
    source_chunk_id: str | None = None
    excerpt: str = Field(min_length=1, max_length=10_000)
    location: str | None = Field(default=None, max_length=1000)
    relationship_type: str = Field(pattern="^(supports|contradicts|contextualizes|uncertain)$")
    confidence: float | None = Field(default=None, ge=0, le=1)
    origin: str = Field(default="user", pattern="^(user|system|model_suggestion)$")
    notes: str | None = Field(default=None, max_length=5000)


class EvidenceRead(ORMModel):
    id: str
    claim_id: str
    source_id: str
    source_chunk_id: str | None
    excerpt: str
    location: str | None
    relationship_type: str
    confidence: float | None
    origin: str
    source_revision: int
    notes: str | None
    created_at: datetime
    source_title: str | None = None


class ClaimRead(ORMModel):
    id: str
    project_id: str
    text: str
    claim_type: str
    status: str
    confidence: float | None
    user_notes: str | None
    created_at: datetime
    updated_at: datetime
    evidence: list[EvidenceRead] = []


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=100_000)
    source_id: str | None = None
    claim_id: str | None = None
    timeline_event_id: str | None = None


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    content: str | None = Field(default=None, min_length=1, max_length=100_000)
    source_id: str | None = None
    claim_id: str | None = None
    timeline_event_id: str | None = None


class NoteRead(ORMModel):
    id: str
    project_id: str
    title: str
    content: str
    source_id: str | None
    claim_id: str | None
    timeline_event_id: str | None
    created_at: datetime
    updated_at: datetime


class TimelineEvidenceCreate(BaseModel):
    source_id: str
    source_chunk_id: str | None = None
    excerpt: str = Field(min_length=1, max_length=10_000)
    location: str | None = None


class TimelineEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    date_start: date | None = None
    date_end: date | None = None
    date_label: str | None = Field(default=None, max_length=120)
    date_precision: str = Field(pattern="^(exact_day|month|year|approximate|unknown)$")
    description: str = Field(min_length=1, max_length=20_000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    origin: str = Field(default="user", pattern="^(user|system|model_suggestion)$")
    review_status: str = Field(default="accepted", pattern="^(suggested|accepted|rejected)$")
    sort_order: int = 0
    evidence: list[TimelineEvidenceCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def preserve_precision(self) -> TimelineEventCreate:
        if self.date_precision == "unknown" and self.date_start is not None:
            raise ValueError("unknown precision cannot include an exact start date")
        if self.date_precision == "approximate" and not self.date_label:
            raise ValueError("approximate dates require the original date label")
        if self.origin == "model_suggestion" and self.review_status != "suggested":
            raise ValueError("model-suggested events must remain suggested until reviewed")
        return self


class TimelineEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    date_start: date | None = None
    date_end: date | None = None
    date_label: str | None = Field(default=None, max_length=120)
    date_precision: str | None = Field(
        default=None, pattern="^(exact_day|month|year|approximate|unknown)$"
    )
    description: str | None = Field(default=None, min_length=1, max_length=20_000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    review_status: str | None = Field(default=None, pattern="^(suggested|accepted|rejected)$")
    sort_order: int | None = None


class TimelineEvidenceRead(ORMModel):
    id: str
    source_id: str
    source_chunk_id: str | None
    source_revision: int
    excerpt: str
    location: str | None


class TimelineEventRead(ORMModel):
    id: str
    project_id: str
    title: str
    date_start: date | None
    date_end: date | None
    date_label: str | None
    date_precision: str
    description: str
    confidence: float | None
    origin: str
    review_status: str
    sort_order: int
    created_at: datetime
    updated_at: datetime
    evidence: list[TimelineEvidenceRead] = []


class ConversationCreate(BaseModel):
    title: str = Field(default="Research conversation", min_length=1, max_length=240)
    selected_source_ids: list[str] = Field(default_factory=list, max_length=100)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    selected_source_ids: list[str] | None = Field(default=None, max_length=100)


class CitationRead(ORMModel):
    id: str
    source_id: str
    source_chunk_id: str
    source_revision: int
    marker: str
    excerpt: str
    location: str | None
    source_title: str | None = None


class MessageRead(ORMModel):
    id: str
    role: str
    content: str
    generated: bool
    warning: str | None
    created_at: datetime
    citations: list[CitationRead] = []


class ConversationRead(ORMModel):
    id: str
    project_id: str
    title: str
    selected_source_ids: list[str]
    created_at: datetime
    updated_at: datetime
    messages: list[MessageRead] = []


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=5000)
    selected_source_ids: list[str] = Field(default_factory=list, max_length=100)
    retrieval_mode: str = Field(default="hybrid", pattern="^(lexical|semantic|hybrid)$")


class AnswerResponse(BaseModel):
    user_message: MessageRead
    answer_message: MessageRead
    retrieved: list[SearchResult]
    provider_available: bool


class BriefCreate(BaseModel):
    title: str = Field(default="Research brief", min_length=1, max_length=240)


class BriefSectionRead(ORMModel):
    id: str
    section_type: str
    title: str
    content: str
    ordinal: int
    origin: str
    user_edited: bool
    generation_warning: str | None
    updated_at: datetime


class BriefRead(ORMModel):
    id: str
    project_id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    sections: list[BriefSectionRead]


class BriefSectionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    content: str | None = Field(default=None, max_length=100_000)
    ordinal: int | None = Field(default=None, ge=0)


class GenerateSectionRequest(BaseModel):
    force_replace_user_edit: bool = False

from __future__ import annotations

from datetime import date, datetime

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from app.models.entities import ProcessingStatus, SourceType
from app.schemas.common import ORMModel


class WebSourceCreate(BaseModel):
    url: AnyHttpUrl


class NoteSourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=2_000_000)


class SourceUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    author: str | None = Field(default=None, max_length=500)
    publisher: str | None = Field(default=None, max_length=500)
    publication_date: date | None = None
    category: str | None = Field(default=None, max_length=120)
    importance: str | None = Field(default=None, pattern="^(low|normal|high|critical)$")
    trust_note: str | None = Field(default=None, max_length=5000)
    source_label: str | None = Field(default=None, pattern="^(primary|secondary|unknown)$")


class SourceCorrection(BaseModel):
    corrected_text: str = Field(min_length=1, max_length=2_000_000)
    correction_note: str = Field(min_length=3, max_length=5000)

    @field_validator("correction_note")
    @classmethod
    def clean_correction_note(cls, value: str) -> str:
        if len(cleaned := value.strip()) < 3:
            raise ValueError(
                "correction_note must contain at least three non-whitespace characters"
            )
        return cleaned


class DuplicateRead(ORMModel):
    id: str
    related_source_id: str
    duplicate_type: str
    similarity: float
    reason: str
    confidence: float


class ProcessingJobRead(ORMModel):
    id: str
    source_id: str
    status: str
    stage: str
    progress: float
    attempt: int
    recovery_count: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class SourceRead(ORMModel):
    id: str
    project_id: str
    source_type: SourceType
    original_name: str
    normalized_url: str | None
    final_url: str | None
    title: str | None
    author: str | None
    publisher: str | None
    publication_date: date | None
    publication_date_is_explicit: bool
    retrieved_at: datetime | None
    content_hash: str | None
    extraction_method: str | None
    processing_status: ProcessingStatus
    warnings: list[str]
    error_message: str | None
    mime_type: str | None
    http_status: int | None
    redirect_count: int
    category: str | None
    importance: str | None
    trust_note: str | None
    source_label: str | None
    created_at: datetime
    updated_at: datetime
    chunk_count: int = 0
    duplicate_warnings: list[DuplicateRead] = Field(default_factory=list)
    processing_job: ProcessingJobRead | None = None


class SourceCorrectionRevisionRead(ORMModel):
    id: str
    revision: int
    correction_note: str
    previous_text_hash: str
    corrected_text_hash: str
    alignment_method: str
    alignment_confidence: float
    location_status: str
    created_at: datetime


class SourceContent(ORMModel):
    source_id: str
    raw_text: str
    normalized_text: str
    corrected_text: str | None
    correction_note: str | None
    correction_revision: int
    correction_history: list[SourceCorrectionRevisionRead] = Field(default_factory=list)
    page_count: int | None


class SourceLocation(BaseModel):
    page_number: int | None = None
    heading_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: str = Field(default="hybrid", pattern="^(lexical|semantic|hybrid)$")
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    source_types: list[SourceType] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    phrase: bool = False
    limit: int = Field(default=12, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        if not (cleaned := value.strip()):
            raise ValueError("query must not be blank")
        return cleaned


class SearchResult(BaseModel):
    chunk_id: str
    source_id: str
    source_title: str
    source_type: SourceType
    location: SourceLocation
    excerpt: str
    score: float
    method: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    warnings: list[str] = Field(default_factory=list)

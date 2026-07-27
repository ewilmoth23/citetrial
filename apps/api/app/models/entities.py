from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class ProjectStatus(str, enum.Enum):
    draft = "draft"
    collecting_sources = "collecting_sources"
    analyzing = "analyzing"
    ready = "ready"
    archived = "archived"


class SourceType(str, enum.Enum):
    webpage = "webpage"
    pdf = "pdf"
    markdown = "markdown"
    text = "text"
    note = "note"


class ProcessingStatus(str, enum.Enum):
    queued = "queued"
    retrieving = "retrieving"
    uploaded = "uploaded"
    extracting = "extracting"
    indexing = "indexing"
    ready = "ready"
    ready_with_warnings = "ready_with_warnings"
    failed = "failed"


class ResearchProject(Base):
    __tablename__ = "research_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240), index=True)
    primary_question: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.draft)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    sources: Mapped[list[Source]] = relationship(
        cascade="all, delete-orphan", back_populates="project"
    )
    claims: Mapped[list[Claim]] = relationship(
        cascade="all, delete-orphan", back_populates="project"
    )
    notes: Mapped[list[ResearchNote]] = relationship(
        cascade="all, delete-orphan", back_populates="project"
    )
    timeline_events: Mapped[list[TimelineEvent]] = relationship(
        cascade="all, delete-orphan", back_populates="project"
    )
    briefs: Mapped[list[ResearchBrief]] = relationship(
        cascade="all, delete-orphan", back_populates="project"
    )
    activities: Mapped[list[ProjectActivity]] = relationship(cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_project_status", "project_id", "processing_status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType))
    original_name: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str | None] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[date | None] = mapped_column(Date)
    publication_date_is_explicit: Mapped[bool] = mapped_column(Boolean, default=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    extraction_method: Mapped[str | None] = mapped_column(String(80))
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus), default=ProcessingStatus.queued
    )
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    http_status: Mapped[int | None] = mapped_column(Integer)
    redirect_count: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    category: Mapped[str | None] = mapped_column(String(120))
    importance: Mapped[str | None] = mapped_column(String(40))
    trust_note: Mapped[str | None] = mapped_column(Text)
    source_label: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    project: Mapped[ResearchProject] = relationship(back_populates="sources")
    document: Mapped[SourceDocument | None] = relationship(
        cascade="all, delete-orphan", back_populates="source", uselist=False
    )
    sections: Mapped[list[SourceSection]] = relationship(
        cascade="all, delete-orphan", back_populates="source"
    )
    chunks: Mapped[list[SourceChunk]] = relationship(
        cascade="all, delete-orphan", back_populates="source"
    )
    correction_revisions: Mapped[list[SourceCorrectionRevision]] = relationship(
        cascade="all, delete-orphan",
        back_populates="source",
        order_by="SourceCorrectionRevision.revision",
    )
    processing_jobs: Mapped[list[ProcessingJob]] = relationship(
        cascade="all, delete-orphan",
        back_populates="source",
        order_by="ProcessingJob.created_at.desc()",
    )
    duplicates: Mapped[list[SourceDuplicateRelation]] = relationship(
        cascade="all, delete-orphan", foreign_keys="SourceDuplicateRelation.source_id"
    )


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), unique=True
    )
    raw_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    corrected_text: Mapped[str | None] = mapped_column(Text)
    correction_note: Mapped[str | None] = mapped_column(Text)
    correction_revision: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int | None] = mapped_column(Integer)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    source: Mapped[Source] = relationship(back_populates="document")


class SourceCorrectionRevision(Base):
    __tablename__ = "source_correction_revisions"
    __table_args__ = (
        UniqueConstraint("source_id", "revision", name="uq_source_correction_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    corrected_text: Mapped[str] = mapped_column(Text)
    correction_note: Mapped[str] = mapped_column(Text)
    previous_text_hash: Mapped[str] = mapped_column(String(64))
    corrected_text_hash: Mapped[str] = mapped_column(String(64))
    alignment_method: Mapped[str] = mapped_column(String(80))
    alignment_confidence: Mapped[float] = mapped_column(Float)
    location_status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    source: Mapped[Source] = relationship(back_populates="correction_revisions")


class SourceSection(Base):
    __tablename__ = "source_sections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    heading_path: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    line_start: Mapped[int | None] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)

    source: Mapped[Source] = relationship(back_populates="sections")


class SourceChunk(Base):
    __tablename__ = "source_chunks"
    __table_args__ = (
        UniqueConstraint("source_id", "content_hash", name="uq_source_chunk_hash"),
        Index("ix_chunks_project_source", "project_id", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    heading_path: Mapped[str | None] = mapped_column(Text)
    line_start: Mapped[int | None] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    source: Mapped[Source] = relationship(back_populates="chunks")


class SourceDuplicateRelation(Base):
    __tablename__ = "source_duplicate_relations"
    __table_args__ = (UniqueConstraint("source_id", "related_source_id", name="uq_duplicate_pair"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    related_source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    duplicate_type: Mapped[str] = mapped_column(String(40))
    similarity: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(40), default="factual")
    status: Mapped[str] = mapped_column(String(40), default="proposed")
    confidence: Mapped[float | None] = mapped_column(Float)
    user_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    project: Mapped[ResearchProject] = relationship(back_populates="claims")
    evidence: Mapped[list[ClaimEvidence]] = relationship(
        cascade="all, delete-orphan", back_populates="claim"
    )


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    source_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_chunks.id", ondelete="SET NULL")
    )
    excerpt: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    relationship_type: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float | None] = mapped_column(Float)
    origin: Mapped[str] = mapped_column(String(20), default="user")
    source_revision: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    claim: Mapped[Claim] = relationship(back_populates="evidence")
    source: Mapped[Source] = relationship()


class ResearchNote(Base):
    __tablename__ = "research_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    claim_id: Mapped[str | None] = mapped_column(ForeignKey("claims.id", ondelete="SET NULL"))
    timeline_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("timeline_events.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    project: Mapped[ResearchProject] = relationship(back_populates="notes")


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    date_start: Mapped[date | None] = mapped_column(Date)
    date_end: Mapped[date | None] = mapped_column(Date)
    date_label: Mapped[str | None] = mapped_column(String(120))
    date_precision: Mapped[str] = mapped_column(String(30), default="unknown")
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    origin: Mapped[str] = mapped_column(String(20), default="user")
    review_status: Mapped[str] = mapped_column(String(20), default="accepted")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    project: Mapped[ResearchProject] = relationship(back_populates="timeline_events")
    evidence: Mapped[list[TimelineEvidence]] = relationship(
        cascade="all, delete-orphan", back_populates="event"
    )


class TimelineEvidence(Base):
    __tablename__ = "timeline_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    timeline_event_id: Mapped[str] = mapped_column(
        ForeignKey("timeline_events.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    source_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_chunks.id", ondelete="SET NULL")
    )
    source_revision: Mapped[int] = mapped_column(Integer, default=0)
    excerpt: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)

    event: Mapped[TimelineEvent] = relationship(back_populates="evidence")
    source: Mapped[Source] = relationship()


class ResearchBrief(Base):
    __tablename__ = "research_briefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(240), default="Research brief")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    project: Mapped[ResearchProject] = relationship(back_populates="briefs")
    sections: Mapped[list[BriefSection]] = relationship(
        cascade="all, delete-orphan", back_populates="brief", order_by="BriefSection.ordinal"
    )


class BriefSection(Base):
    __tablename__ = "brief_sections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    brief_id: Mapped[str] = mapped_column(
        ForeignKey("research_briefs.id", ondelete="CASCADE"), index=True
    )
    section_type: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text, default="")
    ordinal: Mapped[int] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(20), default="generated")
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    generation_warning: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    brief: Mapped[ResearchBrief] = relationship(back_populates="sections")


class ResearchConversation(Base):
    __tablename__ = "research_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(240), default="Research conversation")
    selected_source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )
    messages: Mapped[list[Message]] = relationship(
        cascade="all, delete-orphan", back_populates="conversation"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("research_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    generated: Mapped[bool] = mapped_column(Boolean, default=False)
    warning: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    conversation: Mapped[ResearchConversation] = relationship(back_populates="messages")
    citations: Mapped[list[Citation]] = relationship(
        cascade="all, delete-orphan", back_populates="message"
    )


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    source_chunk_id: Mapped[str] = mapped_column(ForeignKey("source_chunks.id", ondelete="CASCADE"))
    marker: Mapped[str] = mapped_column(String(80))
    excerpt: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    source_revision: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[Message] = relationship(back_populates="citations")
    source: Mapped[Source] = relationship()


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index(
            "uq_processing_jobs_active_source",
            "source_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    stage: Mapped[str] = mapped_column(String(50), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    recovery_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[Source] = relationship(back_populates="processing_jobs")


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    task: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    warning: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExportedReport(Base):
    __tablename__ = "exported_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    format: Mapped[str] = mapped_column(String(20))
    include_full_text: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProjectActivity(Base):
    __tablename__ = "project_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ApplicationSetting(Base):
    __tablename__ = "application_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

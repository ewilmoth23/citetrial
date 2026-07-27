from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from difflib import SequenceMatcher

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.extraction.pdf import extract_pdf
from app.extraction.text import extract_markdown, extract_plain_text
from app.extraction.types import ExtractedDocument, ExtractedSection
from app.extraction.webpage import extract_webpage
from app.ingestion.chunking import chunk_sections
from app.ingestion.corrections import CorrectionAlignment, align_pdf_correction
from app.ingestion.storage import read_upload
from app.ingestion.web import retrieve_webpage
from app.models.entities import (
    ProcessingJob,
    ProcessingStatus,
    ProjectActivity,
    Source,
    SourceChunk,
    SourceCorrectionRevision,
    SourceDocument,
    SourceDuplicateRelation,
    SourceSection,
    SourceType,
    now_utc,
)
from app.retrieval.embeddings import deterministic_embedding

logger = get_logger(__name__)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _record_duplicate_relations(db: Session, source: Source, document: ExtractedDocument) -> None:
    other_sources = db.scalars(
        select(Source).where(
            Source.project_id == source.project_id,
            Source.id != source.id,
            Source.content_hash.is_not(None),
        )
    ).all()
    for other in other_sources:
        if other.content_hash == source.content_hash:
            relation = SourceDuplicateRelation(
                source_id=source.id,
                related_source_id=other.id,
                duplicate_type="exact_content",
                similarity=1.0,
                reason="The normalized source content has the same SHA-256 hash.",
                confidence=1.0,
            )
            source.warnings = [*source.warnings, f"Exact duplicate of source {other.id}."]
            db.add(relation)
            continue
        if not other.document:
            continue
        left = document.normalized_text[:50_000]
        right = other.document.normalized_text[:50_000]
        similarity = SequenceMatcher(None, left, right, autojunk=False).ratio()
        if similarity >= 0.88:
            db.add(
                SourceDuplicateRelation(
                    source_id=source.id,
                    related_source_id=other.id,
                    duplicate_type="near_duplicate",
                    similarity=round(similarity, 4),
                    reason="Normalized text similarity exceeds the project warning threshold.",
                    confidence=round(similarity, 4),
                )
            )
            source.warnings = [*source.warnings, f"Possible near-duplicate of source {other.id}."]


def _replace_sections(
    db: Session, source: Source, sections: list[ExtractedSection], *, delete_existing: bool = False
) -> None:
    if delete_existing:
        db.execute(delete(SourceSection).where(SourceSection.source_id == source.id))
    for ordinal, section in enumerate(sections):
        db.add(
            SourceSection(
                source_id=source.id,
                ordinal=ordinal,
                content=section.content,
                page_number=section.page_number,
                heading_path=section.heading_path,
                line_start=section.line_start,
                line_end=section.line_end,
            )
        )


def _activate_chunks(
    db: Session,
    source: Source,
    sections: list[ExtractedSection],
    settings: Settings,
) -> int:
    existing = {
        item.content_hash: item
        for item in db.scalars(select(SourceChunk).where(SourceChunk.source_id == source.id)).all()
    }
    chunks = chunk_sections(sections, settings.chunk_size, settings.chunk_overlap)
    for ordinal, chunk in enumerate(chunks):
        record = existing.get(chunk.content_hash)
        if record is None:
            record = SourceChunk(
                project_id=source.project_id,
                source_id=source.id,
                content_hash=chunk.content_hash,
            )
            db.add(record)
        record.ordinal = ordinal
        record.content = chunk.content
        record.char_start = chunk.char_start
        record.char_end = chunk.char_end
        record.page_number = chunk.page_number
        record.heading_path = chunk.heading_path
        record.line_start = chunk.line_start
        record.line_end = chunk.line_end
        record.embedding = deterministic_embedding(chunk.content)
        record.is_active = True
        db.flush()
        db.execute(
            text("DELETE FROM source_chunks_fts WHERE chunk_id = :chunk_id"),
            {"chunk_id": record.id},
        )
        db.execute(
            text(
                "INSERT INTO source_chunks_fts(chunk_id, project_id, source_id, content) "
                "VALUES (:chunk_id, :project_id, :source_id, :content)"
            ),
            {
                "chunk_id": record.id,
                "project_id": source.project_id,
                "source_id": source.id,
                "content": record.content,
            },
        )
    return len(chunks)


def index_document(
    db: Session,
    source: Source,
    extracted: ExtractedDocument,
    settings: Settings,
    *,
    record_duplicates: bool = True,
) -> None:
    if len(extracted.normalized_text) > settings.max_extracted_chars:
        raise ValueError("Extracted text exceeds the configured size limit")
    source.processing_status = ProcessingStatus.indexing
    db.flush()
    source.document = SourceDocument(
        raw_text=extracted.raw_text,
        normalized_text=extracted.normalized_text,
        correction_revision=0,
        page_count=extracted.page_count,
        extra_metadata=extracted.metadata,
    )
    _replace_sections(db, source, extracted.sections)
    chunk_count = _activate_chunks(db, source, extracted.sections, settings)
    if record_duplicates:
        source.content_hash = _content_hash(extracted.normalized_text)
    source.extraction_method = extracted.method
    source.title = extracted.title or source.title or source.original_name
    source.author = extracted.author or source.author
    source.publisher = extracted.publisher or source.publisher
    source.publication_date = extracted.publication_date or source.publication_date
    source.publication_date_is_explicit = extracted.publication_date_is_explicit
    source.warnings = list(dict.fromkeys([*source.warnings, *extracted.warnings]))
    if record_duplicates:
        _record_duplicate_relations(db, source, extracted)
    source.processing_status = (
        ProcessingStatus.ready_with_warnings if source.warnings else ProcessingStatus.ready
    )
    source.error_message = None
    db.add(
        ProjectActivity(
            project_id=source.project_id, action="source_processed", detail=source.title
        )
    )
    logger.info(
        "source_indexed",
        source_id=source.id,
        chunk_count=chunk_count,
        warning_count=len(source.warnings),
    )


def _processing_context(db: Session, job_id: str) -> tuple[ProcessingJob, Source] | None:
    job = db.get(ProcessingJob, job_id)
    if job is None or job.status != "running":
        return None
    source = db.get(Source, job.source_id)
    return (job, source) if source is not None else None


def _set_processing_stage(
    db: Session,
    job: ProcessingJob,
    source: Source,
    *,
    stage: str,
    progress: float,
    source_status: ProcessingStatus,
) -> None:
    job.stage = stage
    job.progress = progress
    job.error = None
    source.processing_status = source_status
    source.error_message = None
    db.commit()


def _complete_processing_job(db: Session, job: ProcessingJob) -> None:
    job.status = "complete"
    job.stage = "complete"
    job.progress = 1.0
    job.error = None
    job.completed_at = now_utc()


def _fail_processing_job(job_id: str, stage: str, exc: Exception) -> None:
    message = (str(exc).strip() or type(exc).__name__)[:4000]
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return
        source = db.get(Source, job.source_id)
        job.status = "failed"
        job.stage = stage
        job.error = message
        job.completed_at = now_utc()
        if source is not None:
            source.processing_status = ProcessingStatus.failed
            source.error_message = message
            db.add(
                ProjectActivity(
                    project_id=source.project_id,
                    action="source_processing_failed",
                    detail=f"{source.id}:{stage}",
                )
            )
        db.commit()
        logger.warning(
            "source_processing_failed",
            source_id=job.source_id,
            job_id=job.id,
            stage=stage,
            error_type=type(exc).__name__,
        )


def process_uploaded_job(job_id: str, settings: Settings) -> None:
    stage = "extracting"
    try:
        with SessionLocal() as db:
            context = _processing_context(db, job_id)
            if context is None:
                return
            job, source = context
            _set_processing_stage(
                db,
                job,
                source,
                stage=stage,
                progress=0.2,
                source_status=ProcessingStatus.extracting,
            )
            data = read_upload(source.storage_key or "", settings)
            if source.source_type == SourceType.pdf:
                extracted = extract_pdf(
                    data,
                    max_pages=settings.max_pdf_pages,
                    max_chars=settings.max_extracted_chars,
                )
            elif source.source_type == SourceType.markdown:
                extracted = extract_markdown(data)
            elif source.source_type == SourceType.text:
                extracted = extract_plain_text(data)
            else:
                raise ValueError("Source type is not an uploaded file")
            stage = "indexing"
            _set_processing_stage(
                db,
                job,
                source,
                stage=stage,
                progress=0.75,
                source_status=ProcessingStatus.indexing,
            )
            index_document(db, source, extracted, settings)
            _complete_processing_job(db, job)
            db.commit()
    except Exception as exc:
        _fail_processing_job(job_id, stage, exc)


def _index_web_extraction(
    job_id: str,
    extracted: ExtractedDocument,
    settings: Settings,
) -> None:
    with SessionLocal() as db:
        context = _processing_context(db, job_id)
        if context is None:
            return
        job, source = context
        _set_processing_stage(
            db,
            job,
            source,
            stage="indexing",
            progress=0.75,
            source_status=ProcessingStatus.indexing,
        )
        index_document(db, source, extracted, settings)
        _complete_processing_job(db, job)
        db.commit()


async def process_web_job(job_id: str, settings: Settings) -> None:
    stage = "retrieving"
    try:
        with SessionLocal() as db:
            context = _processing_context(db, job_id)
            if context is None:
                return
            job, source = context
            _set_processing_stage(
                db,
                job,
                source,
                stage=stage,
                progress=0.1,
                source_status=ProcessingStatus.retrieving,
            )
            url = source.normalized_url or source.original_name
        retrieved = await retrieve_webpage(url, settings)
        stage = "extracting"
        with SessionLocal() as db:
            context = _processing_context(db, job_id)
            if context is None:
                return
            job, source = context
            source.final_url = retrieved.final_url
            source.redirect_count = retrieved.redirect_count
            source.http_status = retrieved.status_code
            source.mime_type = retrieved.mime_type
            source.retrieved_at = datetime.now(UTC)
            _set_processing_stage(
                db,
                job,
                source,
                stage=stage,
                progress=0.45,
                source_status=ProcessingStatus.extracting,
            )
        extracted = await asyncio.to_thread(
            extract_webpage,
            retrieved.content,
            encoding=retrieved.encoding,
            max_chars=settings.max_extracted_chars,
        )
        stage = "indexing"
        await asyncio.to_thread(_index_web_extraction, job_id, extracted, settings)
    except Exception as exc:
        await asyncio.to_thread(_fail_processing_job, job_id, stage, exc)


def _correction_alignment(
    source: Source,
    previous_text: str,
    corrected_text: str,
    previous_sections: list[ExtractedSection],
) -> CorrectionAlignment:
    if source.source_type == SourceType.pdf:
        return align_pdf_correction(previous_text, corrected_text, previous_sections)
    if source.source_type in {SourceType.markdown, SourceType.webpage}:
        parsed = extract_markdown(corrected_text.encode())
        return CorrectionAlignment(
            sections=parsed.sections,
            method="markdown-reparse-v1",
            confidence=1.0,
            location_status="reparsed",
            warnings=[],
        )
    parsed = extract_plain_text(corrected_text.encode())
    return CorrectionAlignment(
        sections=parsed.sections,
        method="plain-text-reparse-v1",
        confidence=1.0,
        location_status="reparsed",
        warnings=[],
    )


def _without_correction_warnings(warnings: list[str]) -> list[str]:
    prefixes = (
        "Search index uses a user-corrected extraction.",
        "Corrected PDF text was aligned",
        "The correction changed too much text",
        "Original PDF section boundaries could not be recovered",
    )
    return [warning for warning in warnings if not warning.startswith(prefixes)]


def reindex_corrected_document(
    db: Session,
    source: Source,
    corrected_text: str,
    correction_note: str,
    settings: Settings,
) -> None:
    if not source.document:
        raise ValueError("Source does not contain extracted text")
    document = source.document
    previous_text = document.corrected_text or document.normalized_text
    previous_sections = [
        ExtractedSection(
            content=section.content,
            heading_path=section.heading_path,
            page_number=section.page_number,
            line_start=section.line_start,
            line_end=section.line_end,
        )
        for section in sorted(source.sections, key=lambda item: item.ordinal)
    ]
    alignment = _correction_alignment(source, previous_text, corrected_text, previous_sections)
    revision = document.correction_revision + 1

    db.execute(
        text("DELETE FROM source_chunks_fts WHERE source_id = :source_id"),
        {"source_id": source.id},
    )
    db.execute(
        update(SourceChunk).where(SourceChunk.source_id == source.id).values(is_active=False)
    )
    _replace_sections(db, source, alignment.sections, delete_existing=True)
    db.flush()
    chunk_count = _activate_chunks(db, source, alignment.sections, settings)

    document.corrected_text = corrected_text
    document.correction_note = correction_note
    document.correction_revision = revision
    db.add(
        SourceCorrectionRevision(
            source_id=source.id,
            revision=revision,
            corrected_text=corrected_text,
            correction_note=correction_note,
            previous_text_hash=_content_hash(previous_text),
            corrected_text_hash=_content_hash(corrected_text),
            alignment_method=alignment.method,
            alignment_confidence=alignment.confidence,
            location_status=alignment.location_status,
        )
    )
    base_method = (source.extraction_method or "unknown").split("+user-correction", 1)[0]
    source.extraction_method = f"{base_method}+user-correction"
    source.warnings = list(
        dict.fromkeys(
            [
                *_without_correction_warnings(source.warnings),
                "Search index uses a user-corrected extraction.",
                *alignment.warnings,
            ]
        )
    )
    source.processing_status = (
        ProcessingStatus.ready_with_warnings if source.warnings else ProcessingStatus.ready
    )
    logger.info(
        "corrected_source_indexed",
        source_id=source.id,
        revision=revision,
        chunk_count=chunk_count,
        location_status=alignment.location_status,
    )

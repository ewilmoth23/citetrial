from __future__ import annotations

from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_project, require_source
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.extraction.text import normalize_text
from app.extraction.types import ExtractedDocument, ExtractedSection
from app.ingestion.pipeline import (
    index_document,
    reindex_corrected_document,
)
from app.ingestion.storage import (
    StagedUploadDeletion,
    StorageError,
    persist_upload,
    safe_display_name,
)
from app.ingestion.url_safety import UnsafeUrlError, validate_url
from app.ingestion.worker import enqueue_source_job
from app.models.entities import (
    ProcessingJob,
    ProcessingStatus,
    ProjectActivity,
    ProjectStatus,
    Source,
    SourceType,
)
from app.schemas.common import Page
from app.schemas.source import (
    NoteSourceCreate,
    ProcessingJobRead,
    SourceContent,
    SourceCorrection,
    SourceCorrectionRevisionRead,
    SourceRead,
    SourceUpdate,
    WebSourceCreate,
)

router = APIRouter(prefix="/projects/{project_id}/sources", tags=["sources"])


def source_read(source: Source) -> SourceRead:
    latest_job = (
        max(source.processing_jobs, key=lambda item: (item.attempt, item.id))
        if source.processing_jobs
        else None
    )
    return SourceRead.model_validate(source).model_copy(
        update={
            "chunk_count": sum(1 for chunk in source.chunks if chunk.is_active),
            "duplicate_warnings": source.duplicates,
            "processing_job": (
                ProcessingJobRead.model_validate(latest_job) if latest_job else None
            ),
        }
    )


@router.post("/web", response_model=SourceRead, status_code=status.HTTP_202_ACCEPTED)
async def add_web_source(
    project_id: str,
    payload: WebSourceCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SourceRead:
    project = require_project(db, project_id)
    try:
        validated = await validate_url(str(payload.url), settings)
    except UnsafeUrlError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "unsafe_url", "message": str(exc)}
        ) from exc
    source = Source(
        project_id=project.id,
        source_type=SourceType.webpage,
        original_name=str(payload.url),
        normalized_url=validated.normalized,
        processing_status=ProcessingStatus.queued,
    )
    db.add(source)
    db.flush()
    enqueue_source_job(db, source)
    project.status = ProjectStatus.collecting_sources
    db.add(
        ProjectActivity(
            project_id=project.id, action="source_submitted", detail=validated.normalized
        )
    )
    db.commit()
    db.refresh(source)
    return source_read(source)


@router.post("/upload", response_model=SourceRead, status_code=status.HTTP_202_ACCEPTED)
async def upload_source(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SourceRead:
    project = require_project(db, project_id)
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        storage_key = persist_upload(file.filename or "", data, settings)
    except StorageError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_upload", "message": str(exc)}
        ) from exc
    display_name = safe_display_name(file.filename or "source")
    suffix = Path(display_name).suffix.lower()
    source_type = (
        SourceType.pdf
        if suffix == ".pdf"
        else SourceType.markdown
        if suffix in {".md", ".markdown"}
        else SourceType.text
    )
    source = Source(
        project_id=project.id,
        source_type=source_type,
        original_name=display_name,
        title=Path(display_name).stem,
        storage_key=storage_key,
        mime_type=file.content_type,
        processing_status=ProcessingStatus.queued,
    )
    db.add(source)
    db.flush()
    enqueue_source_job(db, source)
    project.status = ProjectStatus.collecting_sources
    db.add(
        ProjectActivity(project_id=project.id, action="file_uploaded", detail=source.original_name)
    )
    db.commit()
    db.refresh(source)
    return source_read(source)


@router.post("/notes", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_note_source(
    project_id: str,
    payload: NoteSourceCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SourceRead:
    project = require_project(db, project_id)
    source = Source(
        project_id=project.id,
        source_type=SourceType.note,
        original_name=payload.title,
        title=payload.title,
        processing_status=ProcessingStatus.extracting,
    )
    db.add(source)
    db.flush()
    normalized = normalize_text(payload.content)
    index_document(
        db,
        source,
        ExtractedDocument(
            raw_text=payload.content,
            normalized_text=normalized,
            method="user-note",
            sections=[
                ExtractedSection(normalized, line_start=1, line_end=len(normalized.splitlines()))
            ],
            title=payload.title,
        ),
        settings,
    )
    db.commit()
    db.refresh(source)
    return source_read(source)


@router.get("", response_model=Page[SourceRead])
def list_sources(
    project_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[SourceRead]:
    require_project(db, project_id)
    statement = (
        select(Source)
        .where(Source.project_id == project_id)
        .options(
            selectinload(Source.chunks),
            selectinload(Source.duplicates),
            selectinload(Source.processing_jobs),
        )
    )
    items = db.scalars(
        statement.order_by(Source.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = (
        db.scalar(select(func.count()).select_from(Source).where(Source.project_id == project_id))
        or 0
    )
    return Page(
        items=[source_read(item) for item in items], total=total, limit=limit, offset=offset
    )


@router.get("/{source_id}", response_model=SourceRead)
def get_source(project_id: str, source_id: str, db: Session = Depends(get_db)) -> SourceRead:
    source = db.scalar(
        select(Source)
        .where(Source.id == source_id, Source.project_id == project_id)
        .options(
            selectinload(Source.chunks),
            selectinload(Source.duplicates),
            selectinload(Source.processing_jobs),
        )
    )
    if not source:
        raise HTTPException(
            status_code=404, detail={"code": "source_not_found", "message": "Source not found"}
        )
    return source_read(source)


@router.get("/{source_id}/content", response_model=SourceContent)
def source_content(project_id: str, source_id: str, db: Session = Depends(get_db)) -> SourceContent:
    source = require_source(db, project_id, source_id)
    if not source.document:
        raise HTTPException(
            status_code=409,
            detail={"code": "content_unavailable", "message": "Source content is not ready"},
        )
    return SourceContent(
        source_id=source.id,
        raw_text=source.document.raw_text,
        normalized_text=source.document.normalized_text,
        corrected_text=source.document.corrected_text,
        correction_note=source.document.correction_note,
        correction_revision=source.document.correction_revision,
        correction_history=[
            SourceCorrectionRevisionRead.model_validate(item)
            for item in source.correction_revisions
        ],
        page_count=source.document.page_count,
    )


@router.get("/{source_id}/jobs", response_model=list[ProcessingJobRead])
def source_jobs(
    project_id: str,
    source_id: str,
    db: Session = Depends(get_db),
) -> list[ProcessingJob]:
    require_source(db, project_id, source_id)
    return list(
        db.scalars(
            select(ProcessingJob)
            .where(ProcessingJob.source_id == source_id)
            .order_by(ProcessingJob.created_at.desc())
        ).all()
    )


@router.get("/{source_id}/file", response_class=FileResponse)
def source_file(
    project_id: str,
    source_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    source = require_source(db, project_id, source_id)
    if source.source_type != SourceType.pdf or not source.storage_key:
        raise HTTPException(
            status_code=404,
            detail={"code": "file_not_available", "message": "A viewable PDF is not available"},
        )
    path = (settings.upload_dir / source.storage_key).resolve()
    if path.parent != settings.upload_dir.resolve() or not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={"code": "file_not_available", "message": "Stored PDF file is missing"},
        )
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=source.original_name,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )


@router.patch("/{source_id}", response_model=SourceRead)
def update_source(
    project_id: str, source_id: str, payload: SourceUpdate, db: Session = Depends(get_db)
) -> SourceRead:
    source = require_source(db, project_id, source_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, key, value)
    if "publication_date" in payload.model_fields_set:
        source.publication_date_is_explicit = payload.publication_date is not None
    db.add(
        ProjectActivity(project_id=project_id, action="source_metadata_updated", detail=source.id)
    )
    db.commit()
    return source_read(source)


@router.post("/{source_id}/correction", response_model=SourceRead)
def correct_source(
    project_id: str,
    source_id: str,
    payload: SourceCorrection,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SourceRead:
    source = require_source(db, project_id, source_id)
    if not source.document:
        raise HTTPException(
            status_code=409,
            detail={"code": "content_unavailable", "message": "Source content is not ready"},
        )
    corrected_text = normalize_text(payload.corrected_text)
    if not corrected_text:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "empty_correction",
                "message": "Corrected extraction must contain searchable text",
            },
        )
    current_text = source.document.corrected_text or source.document.normalized_text
    if corrected_text == current_text:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "correction_unchanged",
                "message": "Corrected extraction is identical to the current searchable revision",
            },
        )
    reindex_corrected_document(
        db,
        source,
        corrected_text,
        payload.correction_note,
        settings,
    )
    db.add(
        ProjectActivity(
            project_id=project_id, action="source_extraction_corrected", detail=source.id
        )
    )
    db.commit()
    db.refresh(source)
    return source_read(source)


@router.post("/{source_id}/retry", response_model=SourceRead, status_code=status.HTTP_202_ACCEPTED)
def retry_source(
    project_id: str,
    source_id: str,
    db: Session = Depends(get_db),
) -> SourceRead:
    source = require_source(db, project_id, source_id)
    if source.processing_status != ProcessingStatus.failed:
        raise HTTPException(
            status_code=409,
            detail={"code": "retry_not_allowed", "message": "Only failed sources can be retried"},
        )
    if source.source_type not in {
        SourceType.webpage,
        SourceType.pdf,
        SourceType.markdown,
        SourceType.text,
    }:
        raise HTTPException(
            status_code=422,
            detail={"code": "retry_not_supported", "message": "This source type cannot be retried"},
        )
    source.processing_status = ProcessingStatus.queued
    source.error_message = None
    job = enqueue_source_job(db, source)
    db.add(
        ProjectActivity(
            project_id=project_id,
            action="source_retry_queued",
            detail=f"{source.id}:attempt-{job.attempt}",
        )
    )
    db.commit()
    return source_read(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    project_id: str,
    source_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    source = require_source(db, project_id, source_id)
    try:
        staged = StagedUploadDeletion.stage([source.storage_key], settings)
    except StorageError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "deletion_failed", "message": "Source deletion did not start"},
        ) from exc
    try:
        db.execute(
            text("DELETE FROM source_chunks_fts WHERE source_id = :source_id"),
            {"source_id": source_id},
        )
        db.delete(source)
        db.add(ProjectActivity(project_id=project_id, action="source_deleted", detail=source_id))
        db.commit()
    except Exception as exc:
        db.rollback()
        staged.restore()
        raise HTTPException(
            status_code=500,
            detail={"code": "deletion_failed", "message": "Source deletion did not complete"},
        ) from exc
    try:
        staged.finalize()
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "deletion_cleanup_pending",
                "message": "Source records were deleted; secure file cleanup will resume on restart",
            },
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)

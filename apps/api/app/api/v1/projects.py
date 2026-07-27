from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_project
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.session import get_db
from app.ingestion.storage import StagedUploadDeletion, StorageError
from app.models.entities import (
    Claim,
    ProcessingStatus,
    ProjectActivity,
    ProjectStatus,
    ResearchBrief,
    ResearchProject,
    Source,
    TimelineEvent,
)
from app.schemas.common import Page
from app.schemas.project import ActivityRead, ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])
logger = get_logger(__name__)


def project_read(db: Session, project: ResearchProject) -> ProjectRead:
    source_count = (
        db.scalar(select(func.count()).select_from(Source).where(Source.project_id == project.id))
        or 0
    )
    processed = (
        db.scalar(
            select(func.count())
            .select_from(Source)
            .where(
                Source.project_id == project.id,
                Source.processing_status.in_(
                    [ProcessingStatus.ready, ProcessingStatus.ready_with_warnings]
                ),
            )
        )
        or 0
    )
    claim_count = (
        db.scalar(select(func.count()).select_from(Claim).where(Claim.project_id == project.id))
        or 0
    )
    disputed = (
        db.scalar(
            select(func.count())
            .select_from(Claim)
            .where(Claim.project_id == project.id, Claim.status.in_(["disputed", "contradicted"]))
        )
        or 0
    )
    unresolved = (
        db.scalar(
            select(func.count())
            .select_from(Claim)
            .where(
                Claim.project_id == project.id,
                Claim.status.in_(["proposed", "partially_supported", "insufficient_evidence"]),
            )
        )
        or 0
    )
    event_count = (
        db.scalar(
            select(func.count())
            .select_from(TimelineEvent)
            .where(TimelineEvent.project_id == project.id)
        )
        or 0
    )
    latest_brief = db.scalar(
        select(ResearchBrief)
        .where(ResearchBrief.project_id == project.id)
        .order_by(ResearchBrief.updated_at.desc())
    )
    return ProjectRead(
        id=project.id,
        title=project.title,
        primary_question=project.primary_question,
        description=project.description,
        status=project.status,
        created_at=project.created_at,
        updated_at=project.updated_at,
        source_count=source_count,
        processed_source_count=processed,
        claim_count=claim_count,
        disputed_claim_count=disputed,
        unresolved_claim_count=unresolved,
        timeline_event_count=event_count,
        brief_status=latest_brief.status if latest_brief else None,
    )


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    project = ResearchProject(**payload.model_dump(), status=ProjectStatus.draft)
    db.add(project)
    db.flush()
    db.add(ProjectActivity(project_id=project.id, action="project_created", detail=project.title))
    db.commit()
    logger.info("project_created", project_id=project.id)
    return project_read(db, project)


@router.get("", response_model=Page[ProjectRead])
def list_projects(
    include_archived: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[ProjectRead]:
    statement = select(ResearchProject)
    count_statement = select(func.count()).select_from(ResearchProject)
    if not include_archived:
        statement = statement.where(ResearchProject.status != ProjectStatus.archived)
        count_statement = count_statement.where(ResearchProject.status != ProjectStatus.archived)
    projects = db.scalars(
        statement.order_by(ResearchProject.updated_at.desc()).limit(limit).offset(offset)
    ).all()
    return Page(
        items=[project_read(db, item) for item in projects],
        total=db.scalar(count_statement) or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectRead:
    return project_read(db, require_project(db, project_id))


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)
) -> ProjectRead:
    project = require_project(db, project_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    db.add(ProjectActivity(project_id=project.id, action="project_updated", detail=None))
    db.commit()
    return project_read(db, project)


@router.post("/{project_id}/archive", response_model=ProjectRead)
def archive_project(project_id: str, db: Session = Depends(get_db)) -> ProjectRead:
    project = require_project(db, project_id)
    project.status = ProjectStatus.archived
    db.add(ProjectActivity(project_id=project.id, action="project_archived"))
    db.commit()
    return project_read(db, project)


@router.post("/{project_id}/reopen", response_model=ProjectRead)
def reopen_project(project_id: str, db: Session = Depends(get_db)) -> ProjectRead:
    project = require_project(db, project_id)
    project.status = ProjectStatus.ready if project.sources else ProjectStatus.draft
    db.add(ProjectActivity(project_id=project.id, action="project_reopened"))
    db.commit()
    return project_read(db, project)


@router.get("/{project_id}/history", response_model=list[ActivityRead])
def history(project_id: str, db: Session = Depends(get_db)) -> list[ProjectActivity]:
    require_project(db, project_id)
    return list(
        db.scalars(
            select(ProjectActivity)
            .where(ProjectActivity.project_id == project_id)
            .order_by(ProjectActivity.created_at.desc())
        ).all()
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    project = require_project(db, project_id)
    sources = db.scalars(select(Source).where(Source.project_id == project_id)).all()
    try:
        staged = StagedUploadDeletion.stage([source.storage_key for source in sources], settings)
    except StorageError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "deletion_failed", "message": "Project deletion did not start"},
        ) from exc
    try:
        db.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM source_chunks_fts WHERE project_id = :project_id"
            ),
            {"project_id": project_id},
        )
        db.delete(project)
        db.commit()
    except Exception as exc:
        db.rollback()
        staged.restore()
        raise HTTPException(
            status_code=500,
            detail={"code": "deletion_failed", "message": "Project deletion did not complete"},
        ) from exc
    try:
        staged.finalize()
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "deletion_cleanup_pending",
                "message": "Project records were deleted; secure file cleanup will resume on restart",
            },
        ) from exc
    logger.info("project_deleted", project_id=project_id, source_count=len(sources))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

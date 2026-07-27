from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_project
from app.db.session import get_db
from app.models.entities import (
    ProjectActivity,
    Source,
    SourceChunk,
    TimelineEvent,
    TimelineEvidence,
)
from app.research.citations import verify_quotation
from app.schemas.research import TimelineEventCreate, TimelineEventRead, TimelineEventUpdate

router = APIRouter(prefix="/projects/{project_id}/timeline", tags=["timeline"])


def require_event(db: Session, project_id: str, event_id: str) -> TimelineEvent:
    event = db.scalar(
        select(TimelineEvent)
        .where(TimelineEvent.id == event_id, TimelineEvent.project_id == project_id)
        .options(selectinload(TimelineEvent.evidence))
    )
    if event:
        return event
    raise HTTPException(
        status_code=404,
        detail={"code": "timeline_event_not_found", "message": "Timeline event not found"},
    )


@router.post("", response_model=TimelineEventRead, status_code=status.HTTP_201_CREATED)
def create_event(
    project_id: str, payload: TimelineEventCreate, db: Session = Depends(get_db)
) -> TimelineEvent:
    require_project(db, project_id)
    if not payload.evidence:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "evidence_required",
                "message": "Timeline events require a verified source excerpt",
            },
        )
    data = payload.model_dump(exclude={"evidence"})
    event = TimelineEvent(project_id=project_id, **data)
    db.add(event)
    db.flush()
    for evidence in payload.evidence:
        source = db.get(Source, evidence.source_id)
        if not source or source.project_id != project_id or not source.document:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_source", "message": "Timeline evidence source is invalid"},
            )
        chunk = db.get(SourceChunk, evidence.source_chunk_id) if evidence.source_chunk_id else None
        if evidence.source_chunk_id and (
            not chunk
            or not chunk.is_active
            or chunk.project_id != project_id
            or chunk.source_id != source.id
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_chunk",
                    "message": "Timeline evidence chunk does not belong to the selected source",
                },
            )
        stored_text = (
            chunk.content
            if chunk
            else (source.document.corrected_text or source.document.normalized_text)
        )
        if not verify_quotation(evidence.excerpt, stored_text):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "unmatched_evidence",
                    "message": "Timeline evidence does not match stored source text",
                },
            )
        db.add(
            TimelineEvidence(
                timeline_event_id=event.id,
                source_revision=source.document.correction_revision,
                **evidence.model_dump(),
            )
        )
    db.add(ProjectActivity(project_id=project_id, action="timeline_event_created", detail=event.id))
    db.commit()
    return require_event(db, project_id, event.id)


@router.get("", response_model=list[TimelineEventRead])
def list_events(
    project_id: str, review_status: str | None = None, db: Session = Depends(get_db)
) -> list[TimelineEvent]:
    require_project(db, project_id)
    statement = (
        select(TimelineEvent)
        .where(TimelineEvent.project_id == project_id)
        .options(selectinload(TimelineEvent.evidence))
    )
    if review_status:
        statement = statement.where(TimelineEvent.review_status == review_status)
    return list(
        db.scalars(
            statement.order_by(TimelineEvent.date_start.asc(), TimelineEvent.sort_order.asc())
        ).all()
    )


@router.patch("/{event_id}", response_model=TimelineEventRead)
def update_event(
    project_id: str, event_id: str, payload: TimelineEventUpdate, db: Session = Depends(get_db)
) -> TimelineEvent:
    event = require_event(db, project_id, event_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, key, value)
    if event.date_precision == "unknown" and event.date_start:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_date_precision",
                "message": "Unknown dates cannot contain an exact date",
            },
        )
    if event.date_precision == "approximate" and not event.date_label:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_date_precision",
                "message": "Approximate dates require the original label",
            },
        )
    db.commit()
    return require_event(db, project_id, event_id)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(project_id: str, event_id: str, db: Session = Depends(get_db)) -> Response:
    event = require_event(db, project_id, event_id)
    db.delete(event)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

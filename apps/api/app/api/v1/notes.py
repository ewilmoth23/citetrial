from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_project
from app.db.session import get_db
from app.models.entities import Claim, ProjectActivity, ResearchNote, Source, TimelineEvent
from app.schemas.research import NoteCreate, NoteRead, NoteUpdate

router = APIRouter(prefix="/projects/{project_id}/notes", tags=["notes"])


def validate_note_links(
    db: Session,
    project_id: str,
    *,
    source_id: str | None = None,
    claim_id: str | None = None,
    timeline_event_id: str | None = None,
) -> None:
    invalid_field: str | None = None
    if source_id is not None:
        source = db.get(Source, source_id)
        if not source or source.project_id != project_id:
            invalid_field = "source_id"
    if claim_id is not None:
        claim = db.get(Claim, claim_id)
        if not claim or claim.project_id != project_id:
            invalid_field = "claim_id"
    if timeline_event_id is not None:
        event = db.get(TimelineEvent, timeline_event_id)
        if not event or event.project_id != project_id:
            invalid_field = "timeline_event_id"
    if invalid_field:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_note_link",
                "message": f"{invalid_field} must identify a record in this project",
            },
        )


def require_note(db: Session, project_id: str, note_id: str) -> ResearchNote:
    note = db.get(ResearchNote, note_id)
    if note and note.project_id == project_id:
        return note
    raise HTTPException(
        status_code=404, detail={"code": "note_not_found", "message": "Note not found"}
    )


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    project_id: str, payload: NoteCreate, db: Session = Depends(get_db)
) -> ResearchNote:
    require_project(db, project_id)
    validate_note_links(
        db,
        project_id,
        source_id=payload.source_id,
        claim_id=payload.claim_id,
        timeline_event_id=payload.timeline_event_id,
    )
    note = ResearchNote(project_id=project_id, **payload.model_dump())
    db.add(note)
    db.flush()
    db.add(ProjectActivity(project_id=project_id, action="note_created", detail=note.id))
    db.commit()
    return note


@router.get("", response_model=list[NoteRead])
def list_notes(
    project_id: str, query: str | None = None, db: Session = Depends(get_db)
) -> list[ResearchNote]:
    require_project(db, project_id)
    statement = select(ResearchNote).where(ResearchNote.project_id == project_id)
    if query:
        pattern = f"%{query.replace('%', r'\%').replace('_', r'\_')}%"
        statement = statement.where(
            or_(
                ResearchNote.title.ilike(pattern, escape="\\"),
                ResearchNote.content.ilike(pattern, escape="\\"),
            )
        )
    return list(db.scalars(statement.order_by(ResearchNote.updated_at.desc())).all())


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(
    project_id: str, note_id: str, payload: NoteUpdate, db: Session = Depends(get_db)
) -> ResearchNote:
    note = require_note(db, project_id, note_id)
    values = payload.model_dump(exclude_unset=True)
    validate_note_links(
        db,
        project_id,
        source_id=values.get("source_id"),
        claim_id=values.get("claim_id"),
        timeline_event_id=values.get("timeline_event_id"),
    )
    for key, value in values.items():
        setattr(note, key, value)
    db.commit()
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(project_id: str, note_id: str, db: Session = Depends(get_db)) -> Response:
    db.delete(require_note(db, project_id, note_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

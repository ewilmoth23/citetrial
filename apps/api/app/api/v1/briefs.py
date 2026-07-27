from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_project
from app.db.session import get_db
from app.models.entities import BriefSection, ProjectActivity, ResearchBrief
from app.research.briefs import create_brief, deterministic_section
from app.schemas.research import (
    BriefCreate,
    BriefRead,
    BriefSectionRead,
    BriefSectionUpdate,
    GenerateSectionRequest,
)

router = APIRouter(prefix="/projects/{project_id}/briefs", tags=["briefs"])


def require_brief(db: Session, project_id: str, brief_id: str) -> ResearchBrief:
    brief = db.scalar(
        select(ResearchBrief)
        .where(ResearchBrief.id == brief_id, ResearchBrief.project_id == project_id)
        .options(selectinload(ResearchBrief.sections), selectinload(ResearchBrief.project))
    )
    if brief:
        return brief
    raise HTTPException(
        status_code=404, detail={"code": "brief_not_found", "message": "Brief not found"}
    )


@router.post("", response_model=BriefRead, status_code=status.HTTP_201_CREATED)
def create_project_brief(
    project_id: str, payload: BriefCreate, db: Session = Depends(get_db)
) -> ResearchBrief:
    project = require_project(db, project_id)
    brief = create_brief(db, project, payload.title)
    db.add(ProjectActivity(project_id=project_id, action="brief_created", detail=brief.id))
    db.commit()
    return require_brief(db, project_id, brief.id)


@router.get("", response_model=list[BriefRead])
def list_briefs(project_id: str, db: Session = Depends(get_db)) -> list[ResearchBrief]:
    require_project(db, project_id)
    ids = db.scalars(
        select(ResearchBrief.id)
        .where(ResearchBrief.project_id == project_id)
        .order_by(ResearchBrief.updated_at.desc())
    ).all()
    return [require_brief(db, project_id, item) for item in ids]


@router.get("/{brief_id}", response_model=BriefRead)
def get_brief(project_id: str, brief_id: str, db: Session = Depends(get_db)) -> ResearchBrief:
    return require_brief(db, project_id, brief_id)


@router.patch("/{brief_id}/sections/{section_id}", response_model=BriefSectionRead)
def update_section(
    project_id: str,
    brief_id: str,
    section_id: str,
    payload: BriefSectionUpdate,
    db: Session = Depends(get_db),
) -> BriefSection:
    brief = require_brief(db, project_id, brief_id)
    section = next((item for item in brief.sections if item.id == section_id), None)
    if not section:
        raise HTTPException(
            status_code=404,
            detail={"code": "section_not_found", "message": "Brief section not found"},
        )
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(section, key, value)
    if "content" in payload.model_fields_set:
        section.user_edited = True
        section.origin = "user"
    db.commit()
    return section


@router.post("/{brief_id}/sections/{section_id}/generate", response_model=BriefSectionRead)
def generate_section(
    project_id: str,
    brief_id: str,
    section_id: str,
    payload: GenerateSectionRequest,
    db: Session = Depends(get_db),
) -> BriefSection:
    brief = require_brief(db, project_id, brief_id)
    section = next((item for item in brief.sections if item.id == section_id), None)
    if not section:
        raise HTTPException(
            status_code=404,
            detail={"code": "section_not_found", "message": "Brief section not found"},
        )
    if section.user_edited and not payload.force_replace_user_edit:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "user_edit_preserved",
                "message": "This section contains user edits. Confirm replacement explicitly.",
            },
        )
    content, warning = deterministic_section(db, brief, section)
    section.content = content
    section.generation_warning = warning
    section.origin = "generated"
    section.user_edited = False
    db.add(
        ProjectActivity(
            project_id=project_id, action="brief_section_generated", detail=section.section_type
        )
    )
    db.commit()
    return section

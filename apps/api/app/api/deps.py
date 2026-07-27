from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import ResearchProject, Source


def require_project(db: Session, project_id: str) -> ResearchProject:
    if project := db.get(ResearchProject, project_id):
        return project
    raise HTTPException(
        status_code=404, detail={"code": "project_not_found", "message": "Project not found"}
    )


def require_source(db: Session, project_id: str, source_id: str) -> Source:
    source = db.get(Source, source_id)
    if source and source.project_id == project_id:
        return source
    raise HTTPException(
        status_code=404, detail={"code": "source_not_found", "message": "Source not found"}
    )

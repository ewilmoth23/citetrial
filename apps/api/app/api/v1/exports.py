from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import require_project
from app.db.session import get_db
from app.models.entities import ExportedReport, ProjectActivity
from app.services.exports import project_export_data, project_markdown

router = APIRouter(prefix="/projects/{project_id}/exports", tags=["exports"])


@router.get("/markdown")
def export_markdown(
    project_id: str,
    include_notes: bool = True,
    db: Session = Depends(get_db),
) -> Response:
    project = require_project(db, project_id)
    content = project_markdown(db, project, include_notes)
    db.add(ExportedReport(project_id=project_id, format="markdown"))
    db.add(ProjectActivity(project_id=project_id, action="project_exported", detail="markdown"))
    db.commit()
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="citetrail-{project_id}.md"'},
    )


@router.get("/json")
def export_json(
    project_id: str,
    include_full_text: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Response:
    project = require_project(db, project_id)
    content = json.dumps(
        project_export_data(db, project, include_full_text), indent=2, ensure_ascii=False
    )
    db.add(
        ExportedReport(project_id=project_id, format="json", include_full_text=include_full_text)
    )
    db.add(ProjectActivity(project_id=project_id, action="project_exported", detail="json"))
    db.commit()
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="citetrail-{project_id}.json"'},
    )

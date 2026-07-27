from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_project
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.runtime_settings import effective_settings
from app.db.session import get_db
from app.retrieval.search import hybrid_search
from app.schemas.source import SearchRequest, SearchResponse

router = APIRouter(prefix="/projects/{project_id}/search", tags=["search"])
logger = get_logger(__name__)


@router.post("", response_model=SearchResponse)
def search_project(
    project_id: str,
    payload: SearchRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SearchResponse:
    require_project(db, project_id)
    semantic_enabled = effective_settings(settings, db).semantic_search_enabled
    warnings: list[str] = []
    if payload.mode == "semantic" and not semantic_enabled:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "semantic_search_disabled",
                "message": "Semantic search is disabled in application settings",
            },
        )
    effective_payload = payload
    if payload.mode == "hybrid" and not semantic_enabled:
        effective_payload = payload.model_copy(update={"mode": "lexical"})
        warnings.append("Semantic search is disabled; results use full-text retrieval only.")
    started = time.perf_counter()
    try:
        results = hybrid_search(db, project_id, effective_payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_search", "message": str(exc)}
        ) from exc
    logger.info(
        "search_completed",
        project_id=project_id,
        result_count=len(results),
        duration_ms=round((time.perf_counter() - started) * 1000),
    )
    return SearchResponse(query=payload.query, results=results, warnings=warnings)

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import Settings, get_settings
from app.core.runtime_settings import effective_settings
from app.db.session import get_db
from app.models.entities import ProcessingJob
from app.providers.factory import create_provider

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    effective = effective_settings(settings, db)
    checks: dict[str, dict[str, Any]] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "healthy"}
    except Exception:
        checks["database"] = {"status": "unhealthy"}
    try:
        effective.ensure_directories()
        probe = effective.data_dir / ".health"
        probe.touch(exist_ok=True)
        probe.unlink(missing_ok=True)
        checks["storage"] = {"status": "healthy"}
    except OSError:
        checks["storage"] = {"status": "unhealthy"}
    checks["vector_store"] = {
        "status": "healthy" if effective.semantic_search_enabled else "disabled",
        "mode": "local deterministic feature-hash embeddings"
        if effective.semantic_search_enabled
        else None,
    }
    ingestion_worker = getattr(request.app.state, "ingestion_worker", None)
    worker_running = bool(ingestion_worker and ingestion_worker.is_running)
    queue_counts = {
        status: db.scalar(
            select(func.count()).select_from(ProcessingJob).where(ProcessingJob.status == status)
        )
        or 0
        for status in ("queued", "running")
    }
    checks["ingestion_worker"] = {
        "status": "healthy" if worker_running else "unhealthy",
        **queue_counts,
    }
    data_directory_lock = getattr(request.app.state, "data_directory_lock", None)
    checks["data_directory_lock"] = {
        "status": "healthy"
        if data_directory_lock is not None and data_directory_lock.is_acquired
        else "unhealthy",
        "mode": "exclusive single-owner",
    }
    provider = create_provider(effective)
    available, provider_status = await provider.health()
    checks["provider"] = {
        "status": provider_status,
        "provider": effective.model_provider,
        "model": effective.model_name,
        "requests_leave_device": provider.leaves_device,
    }
    essential_healthy = all(
        checks[name]["status"] == "healthy"
        for name in ("database", "storage", "ingestion_worker", "data_directory_lock")
    )
    return {
        "status": "healthy" if essential_healthy else "degraded",
        "version": __version__,
        "checks": checks,
    }

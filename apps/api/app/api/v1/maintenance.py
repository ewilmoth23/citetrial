from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, status
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.session import engine
from app.services.backups import (
    BACKUP_MEDIA_TYPE,
    BackupError,
    backup_filename,
    create_workspace_backup,
)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])
logger = get_logger(__name__)


@router.post("/backups", response_class=FileResponse)
def create_backup(
    intent: str | None = Header(default=None, alias="X-CiteTrail-Intent"),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    if intent != "backup":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "backup_intent_required",
                "message": "An explicit CiteTrail backup intent header is required",
            },
        )

    temporary_dir = Path(tempfile.mkdtemp(prefix="citetrail-backup-response-"))
    filename = backup_filename()
    destination = temporary_dir / filename
    try:
        manifest = create_workspace_backup(settings, engine, destination)
    except BackupError as exc:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "backup_incomplete",
                "message": str(exc),
            },
        ) from exc
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise

    logger.info(
        "workspace_backup_created",
        project_count=manifest.statistics.get("projects", 0),
        source_count=manifest.statistics.get("sources", 0),
        file_count=len(manifest.files),
        archive_bytes=destination.stat().st_size,
    )
    return FileResponse(
        destination,
        media_type=BACKUP_MEDIA_TYPE,
        filename=filename,
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(shutil.rmtree, temporary_dir, ignore_errors=True),
    )

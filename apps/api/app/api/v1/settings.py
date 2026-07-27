from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.runtime_settings import RUNTIME_SETTING_KEYS, effective_settings
from app.db.session import get_db
from app.models.entities import ApplicationSetting
from app.providers.factory import create_provider

router = APIRouter(prefix="/settings", tags=["settings"])

SAFE_KEYS = {"theme", *RUNTIME_SETTING_KEYS}


class SettingsUpdate(BaseModel):
    values: dict[str, Any] = Field(max_length=10)


def safe_settings(settings: Settings, db: Session) -> dict[str, Any]:
    overrides = {
        item.key: item.value for item in db.query(ApplicationSetting).all() if item.key in SAFE_KEYS
    }
    effective = effective_settings(settings, db)
    provider = create_provider(effective)
    return {
        "data_dir": str(effective.data_dir),
        "semantic_search_enabled": effective.semantic_search_enabled,
        "embedding_model": effective.embedding_model,
        "model_provider": effective.model_provider,
        "model_base_url": effective.model_base_url,
        "model_name": effective.model_name,
        "model_api_key_configured": bool(effective.model_api_key),
        "provider_requests_leave_device": provider.leaves_device,
        "remote_provider_warning": "Remote model providers receive the selected source excerpts.",
        "allow_http_urls": effective.allow_http_urls,
        "max_upload_bytes": effective.max_upload_bytes,
        "max_download_bytes": effective.max_download_bytes,
        "request_timeout_seconds": effective.request_timeout_seconds,
        "max_pdf_pages": effective.max_pdf_pages,
        "ingestion_poll_seconds": effective.ingestion_poll_seconds,
        "ingestion_worker_mode": "durable embedded single worker",
        "data_directory_lock_mode": "exclusive single-owner",
        "backup_format": "verified full-workspace .ctbackup",
        "restore_mode": "offline validated restore",
        "ocr_mode": "disabled",
        **({"theme": overrides["theme"]} if "theme" in overrides else {}),
    }


@router.get("")
def get_safe_settings(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    return safe_settings(settings, db)


@router.patch("")
def update_safe_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    unsupported = set(payload.values) - SAFE_KEYS
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unsafe_setting",
                "message": f"Settings cannot be changed through the API: {', '.join(sorted(unsupported))}",
            },
        )
    for key, value in payload.values.items():
        if key == "model_provider" and value not in {"ollama", "openai_compatible"}:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_setting", "message": "Unsupported model provider"},
            )
        if key in {"semantic_search_enabled"} and not isinstance(value, bool):
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_setting", "message": f"{key} must be a boolean"},
            )
        if key in {"model_base_url", "model_name", "theme"} and not isinstance(value, str):
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_setting", "message": f"{key} must be a string"},
            )
        if key == "model_name" and not (1 <= len(value) <= 120):
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_setting", "message": "model_name length is invalid"},
            )
        if key == "theme" and value not in {"light", "dark", "system"}:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_setting", "message": "theme is invalid"},
            )
        item = db.get(ApplicationSetting, key) or ApplicationSetting(key=key, value=value)
        item.value = value
        db.add(item)
    try:
        db.flush()
        response = safe_settings(settings, db)
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_setting", "message": "Settings validation failed"},
        ) from exc
    db.commit()
    return response

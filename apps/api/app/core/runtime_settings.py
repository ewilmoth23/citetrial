from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.entities import ApplicationSetting

RUNTIME_SETTING_KEYS = {
    "semantic_search_enabled",
    "model_provider",
    "model_base_url",
    "model_name",
}


def runtime_overrides(db: Session) -> dict[str, Any]:
    return {
        item.key: item.value
        for item in db.scalars(
            select(ApplicationSetting).where(ApplicationSetting.key.in_(RUNTIME_SETTING_KEYS))
        ).all()
    }


def effective_settings(settings: Settings, db: Session) -> Settings:
    values = settings.model_dump()
    values.update(runtime_overrides(db))
    return Settings.model_validate(values)

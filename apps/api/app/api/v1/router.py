from fastapi import APIRouter

from app.api.v1 import (
    briefs,
    claims,
    conversations,
    exports,
    health,
    maintenance,
    notes,
    projects,
    search,
    settings,
    sources,
    timeline,
)

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(projects.router)
router.include_router(sources.router)
router.include_router(search.router)
router.include_router(conversations.router)
router.include_router(claims.router)
router.include_router(timeline.router)
router.include_router(notes.router)
router.include_router(briefs.router)
router.include_router(exports.router)
router.include_router(settings.router)
router.include_router(maintenance.router)

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1.router import router
from app.core.config import get_settings
from app.core.data_lock import DataDirectoryLock
from app.core.logging import configure_logging, get_logger
from app.db.init_db import init_database
from app.db.session import SessionLocal
from app.ingestion.storage import recover_staged_upload_deletions
from app.ingestion.worker import IngestionWorker

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings.ensure_directories()
    data_directory_lock = DataDirectoryLock(settings.data_dir)
    data_directory_lock.acquire()
    application.state.data_directory_lock = data_directory_lock
    application.state.storage_operation_lock = asyncio.Lock()
    ingestion_worker: IngestionWorker | None = None
    try:
        init_database()
        with SessionLocal() as recovery_db:
            restored_uploads, finalized_uploads = recover_staged_upload_deletions(
                settings, recovery_db
            )
        if restored_uploads or finalized_uploads:
            logger.info(
                "staged_upload_deletions_recovered",
                restored=restored_uploads,
                finalized=finalized_uploads,
            )
        ingestion_worker = IngestionWorker(settings)
        await ingestion_worker.start()
        application.state.ingestion_worker = ingestion_worker
        logger.info(
            "application_started", environment=settings.environment, data_dir=str(settings.data_dir)
        )
        yield
    finally:
        if ingestion_worker is not None:
            await ingestion_worker.stop()
        data_directory_lock.release()
        logger.info("application_stopped")


app = FastAPI(
    title="CiteTrail API",
    description="Local-first, provenance-preserving research workspace API.",
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Request-ID", "X-CiteTrail-Intent"],
)


def _uses_workspace_file_set(request: Request) -> bool:
    path = request.url.path
    if request.method == "POST" and path == "/api/v1/maintenance/backups":
        return True
    if request.method == "POST" and path.endswith("/sources/upload"):
        return True
    return request.method == "DELETE" and path.startswith("/api/v1/projects/")


@app.middleware("http")
async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:128]
    structlog.contextvars.bind_contextvars(request_id=request_id)
    started = time.perf_counter()
    try:
        storage_lock = getattr(request.app.state, "storage_operation_lock", None)
        if storage_lock is not None and _uses_workspace_file_set(request):
            async with storage_lock:
                response = await call_next(request)
        else:
            response = await call_next(request)
    finally:
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        structlog.contextvars.clear_contextvars()
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        detail = exc.detail
    else:
        detail = {"code": "http_error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for item in exc.errors():
        details.append(
            {"location": list(item["loc"]), "message": item["msg"], "type": item["type"]}
        )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": details,
            }
        },
    )


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": "CiteTrail API", "docs": "/docs", "health": "/api/v1/health"}


app.include_router(router)

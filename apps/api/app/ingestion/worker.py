from __future__ import annotations

import asyncio
from contextlib import suppress

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.ingestion.pipeline import process_uploaded_job, process_web_job
from app.models.entities import (
    ProcessingJob,
    ProcessingStatus,
    ProjectActivity,
    Source,
    SourceType,
    now_utc,
)

logger = get_logger(__name__)

_PROCESSABLE_TYPES = {
    SourceType.webpage,
    SourceType.pdf,
    SourceType.markdown,
    SourceType.text,
}
_NONTERMINAL_SOURCE_STATUSES = {
    ProcessingStatus.queued,
    ProcessingStatus.retrieving,
    ProcessingStatus.uploaded,
    ProcessingStatus.extracting,
    ProcessingStatus.indexing,
}


def enqueue_source_job(db: Session, source: Source, *, recovered: bool = False) -> ProcessingJob:
    pending_or_loaded = next(
        (job for job in source.processing_jobs if job.status in {"queued", "running"}),
        None,
    )
    if pending_or_loaded is not None:
        return pending_or_loaded
    active = db.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.source_id == source.id,
            ProcessingJob.status.in_(("queued", "running")),
        )
        .order_by(ProcessingJob.created_at.desc())
    )
    if active is not None:
        return active
    previous_attempt = (
        db.scalar(
            select(func.max(ProcessingJob.attempt)).where(ProcessingJob.source_id == source.id)
        )
        or 0
    )
    job = ProcessingJob(
        source_id=source.id,
        status="queued",
        stage="recovered" if recovered else "queued",
        progress=0.0,
        attempt=previous_attempt + 1,
        recovery_count=1 if recovered else 0,
    )
    source.processing_status = ProcessingStatus.queued
    source.error_message = None
    source.processing_jobs.append(job)
    return job


def recover_interrupted_jobs() -> tuple[int, int]:
    recovered_jobs = 0
    reconstructed_jobs = 0
    with SessionLocal() as db:
        running = db.scalars(select(ProcessingJob).where(ProcessingJob.status == "running")).all()
        for job in running:
            job.status = "queued"
            job.stage = "recovered"
            job.progress = 0.0
            job.error = None
            job.started_at = None
            job.completed_at = None
            job.recovery_count += 1
            source = db.get(Source, job.source_id)
            if source is not None:
                source.processing_status = ProcessingStatus.queued
                source.error_message = None
                db.add(
                    ProjectActivity(
                        project_id=source.project_id,
                        action="source_processing_recovered",
                        detail=f"{source.id}:attempt-{job.attempt}",
                    )
                )
            recovered_jobs += 1

        active_source_ids = set(
            db.scalars(
                select(ProcessingJob.source_id).where(
                    ProcessingJob.status.in_(("queued", "running"))
                )
            ).all()
        )
        stranded_sources = db.scalars(
            select(Source).where(
                Source.source_type.in_(_PROCESSABLE_TYPES),
                Source.processing_status.in_(_NONTERMINAL_SOURCE_STATUSES),
            )
        ).all()
        for source in stranded_sources:
            if source.id in active_source_ids:
                continue
            enqueue_source_job(db, source, recovered=True)
            db.add(
                ProjectActivity(
                    project_id=source.project_id,
                    action="source_processing_reconstructed",
                    detail=source.id,
                )
            )
            active_source_ids.add(source.id)
            reconstructed_jobs += 1
        db.commit()
    return recovered_jobs, reconstructed_jobs


def _claim_next_job() -> str | None:
    with SessionLocal() as db:
        job_id = db.scalar(
            select(ProcessingJob.id)
            .where(ProcessingJob.status == "queued")
            .order_by(ProcessingJob.created_at.asc(), ProcessingJob.id.asc())
            .limit(1)
        )
        if job_id is None:
            return None
        claimed_id = db.scalar(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id, ProcessingJob.status == "queued")
            .values(
                status="running",
                stage="starting",
                started_at=now_utc(),
                completed_at=None,
                error=None,
            )
            .returning(ProcessingJob.id)
        )
        if claimed_id is None:
            db.rollback()
            return None
        db.commit()
        return claimed_id


async def _process_claimed_job(job_id: str, settings: Settings) -> None:
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        source = db.get(Source, job.source_id) if job is not None else None
        source_type = source.source_type if source is not None else None
    if source_type is None:
        return
    if source_type == SourceType.webpage:
        await process_web_job(job_id, settings)
        return
    if source_type in {SourceType.pdf, SourceType.markdown, SourceType.text}:
        await asyncio.to_thread(process_uploaded_job, job_id, settings)
        return
    raise ValueError(f"Source type {source_type.value} cannot be processed asynchronously")


def _mark_unhandled_failure(job_id: str, exc: Exception) -> None:
    message = (str(exc).strip() or type(exc).__name__)[:4000]
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None or job.status != "running":
            return
        source = db.get(Source, job.source_id)
        job.status = "failed"
        job.stage = "worker_error"
        job.error = message
        job.completed_at = now_utc()
        if source is not None:
            source.processing_status = ProcessingStatus.failed
            source.error_message = message
            db.add(
                ProjectActivity(
                    project_id=source.project_id,
                    action="source_processing_failed",
                    detail=f"{source.id}:worker_error",
                )
            )
        db.commit()


class IngestionWorker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running:
            return
        recovered, reconstructed = await asyncio.to_thread(recover_interrupted_jobs)
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="citetrail-ingestion-worker")
        logger.info(
            "ingestion_worker_started",
            recovered_jobs=recovered,
            reconstructed_jobs=reconstructed,
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
        logger.info("ingestion_worker_stopped")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = await asyncio.to_thread(_claim_next_job)
            except Exception as exc:
                logger.exception(
                    "ingestion_worker_claim_failed",
                    error_type=type(exc).__name__,
                )
                with suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=self.settings.ingestion_poll_seconds,
                    )
                continue
            if job_id is not None:
                try:
                    await _process_claimed_job(job_id, self.settings)
                except Exception as exc:
                    await asyncio.to_thread(_mark_unhandled_failure, job_id, exc)
                    logger.exception(
                        "ingestion_worker_job_crashed",
                        job_id=job_id,
                        error_type=type(exc).__name__,
                    )
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.settings.ingestion_poll_seconds,
                )

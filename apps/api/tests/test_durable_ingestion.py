from __future__ import annotations

import time

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.ingestion.pipeline import process_uploaded_job, process_web_job
from app.ingestion.web import RetrievedWebpage
from app.ingestion.worker import enqueue_source_job, recover_interrupted_jobs
from app.models.entities import (
    ProcessingJob,
    ProcessingStatus,
    ResearchProject,
    Source,
    SourceType,
)


def project_record(title: str = "Durable queue") -> ResearchProject:
    return ResearchProject(title=title, primary_question="Will queued work recover?")


def test_enqueue_is_idempotent_and_enforces_one_active_job(db) -> None:
    project = project_record()
    db.add(project)
    db.flush()
    source = Source(
        project_id=project.id,
        source_type=SourceType.pdf,
        original_name="queued.pdf",
        storage_key="queued.pdf",
        processing_status=ProcessingStatus.uploaded,
    )
    db.add(source)
    db.flush()

    first = enqueue_source_job(db, source)
    second = enqueue_source_job(db, source)
    db.commit()

    assert first.id == second.id
    assert first.attempt == 1
    assert source.processing_status == ProcessingStatus.queued
    assert (
        db.scalar(
            select(func.count())
            .select_from(ProcessingJob)
            .where(
                ProcessingJob.source_id == source.id,
                ProcessingJob.status.in_(("queued", "running")),
            )
        )
        == 1
    )


def test_startup_requeues_running_jobs_and_reconstructs_orphans(db) -> None:
    project = project_record()
    db.add(project)
    db.flush()
    interrupted = Source(
        project_id=project.id,
        source_type=SourceType.webpage,
        original_name="https://example.org/interrupted",
        normalized_url="https://example.org/interrupted",
        processing_status=ProcessingStatus.retrieving,
    )
    orphaned = Source(
        project_id=project.id,
        source_type=SourceType.text,
        original_name="orphaned.txt",
        storage_key="orphaned.txt",
        processing_status=ProcessingStatus.indexing,
    )
    db.add_all([interrupted, orphaned])
    db.flush()
    running = ProcessingJob(
        source_id=interrupted.id,
        status="running",
        stage="retrieving",
        progress=0.1,
        attempt=2,
    )
    db.add(running)
    db.commit()

    recovered, reconstructed = recover_interrupted_jobs()

    assert (recovered, reconstructed) == (1, 1)
    db.expire_all()
    stored_running = db.get(ProcessingJob, running.id)
    assert stored_running is not None
    assert stored_running.status == "queued"
    assert stored_running.stage == "recovered"
    assert stored_running.recovery_count == 1
    assert db.get(Source, interrupted.id).processing_status == ProcessingStatus.queued
    orphaned_job = db.scalar(select(ProcessingJob).where(ProcessingJob.source_id == orphaned.id))
    assert orphaned_job is not None
    assert orphaned_job.status == "queued"
    assert orphaned_job.stage == "recovered"
    assert orphaned_job.recovery_count == 1


def test_failed_processing_updates_the_claimed_job_in_place(db) -> None:
    project = project_record()
    db.add(project)
    db.flush()
    source = Source(
        project_id=project.id,
        source_type=SourceType.pdf,
        original_name="missing.pdf",
        storage_key="missing.pdf",
        processing_status=ProcessingStatus.queued,
    )
    db.add(source)
    db.flush()
    job = ProcessingJob(
        source_id=source.id,
        status="running",
        stage="starting",
        progress=0,
        attempt=1,
    )
    db.add(job)
    db.commit()

    process_uploaded_job(job.id, get_settings())

    db.expire_all()
    stored_job = db.get(ProcessingJob, job.id)
    stored_source = db.get(Source, source.id)
    assert stored_job is not None
    assert stored_source is not None
    assert stored_job.status == "failed"
    assert stored_job.stage == "extracting"
    assert stored_job.completed_at is not None
    assert stored_job.error
    assert stored_source.processing_status == ProcessingStatus.failed
    assert stored_source.error_message == stored_job.error
    assert (
        db.scalar(
            select(func.count())
            .select_from(ProcessingJob)
            .where(ProcessingJob.source_id == source.id)
        )
        == 1
    )


async def test_web_job_completes_the_claimed_attempt(monkeypatch, db) -> None:
    project = project_record()
    db.add(project)
    db.flush()
    source = Source(
        project_id=project.id,
        source_type=SourceType.webpage,
        original_name="https://example.org/evidence",
        normalized_url="https://example.org/evidence",
        processing_status=ProcessingStatus.queued,
    )
    db.add(source)
    db.flush()
    job = ProcessingJob(
        source_id=source.id,
        status="running",
        stage="starting",
        progress=0,
        attempt=1,
    )
    db.add(job)
    db.commit()

    async def retrieve(_url: str, _settings) -> RetrievedWebpage:
        return RetrievedWebpage(
            original_url="https://example.org/evidence",
            final_url="https://example.org/final",
            redirect_count=1,
            status_code=200,
            mime_type="text/html",
            content=b"<html><head><title>Durable evidence</title></head><body>"
            b"<main><p>The durable queue retained this webpage.</p></main></body></html>",
            encoding="utf-8",
        )

    monkeypatch.setattr("app.ingestion.pipeline.retrieve_webpage", retrieve)
    await process_web_job(job.id, get_settings())

    db.expire_all()
    stored_job = db.get(ProcessingJob, job.id)
    stored_source = db.get(Source, source.id)
    assert stored_job is not None
    assert stored_source is not None
    assert stored_job.status == "complete"
    assert stored_job.stage == "complete"
    assert stored_job.progress == 1
    assert stored_source.processing_status in {
        ProcessingStatus.ready,
        ProcessingStatus.ready_with_warnings,
    }
    assert stored_source.final_url == "https://example.org/final"
    assert stored_source.document is not None
    assert "durable queue" in stored_source.document.normalized_text.lower()


def test_retry_creates_a_new_auditable_attempt(client: TestClient, db) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"title": "Retry trail", "primary_question": "Does retry preserve history?"},
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    source = Source(
        project_id=project_id,
        source_type=SourceType.pdf,
        original_name="missing-retry.pdf",
        storage_key="missing-retry.pdf",
        processing_status=ProcessingStatus.failed,
        error_message="First attempt failed.",
    )
    db.add(source)
    db.flush()
    first = ProcessingJob(
        source_id=source.id,
        status="failed",
        stage="extracting",
        progress=0.2,
        attempt=1,
        error="First attempt failed.",
    )
    db.add(first)
    db.commit()

    retry = client.post(f"/api/v1/projects/{project_id}/sources/{source.id}/retry")
    assert retry.status_code == 202, retry.text
    assert retry.json()["processing_job"]["attempt"] == 2

    deadline = time.monotonic() + 5
    latest: dict = {}
    while time.monotonic() < deadline:
        latest = client.get(f"/api/v1/projects/{project_id}/sources/{source.id}").json()
        if latest["processing_status"] == "failed":
            break
        time.sleep(0.02)
    assert latest["processing_status"] == "failed"
    jobs = client.get(f"/api/v1/projects/{project_id}/sources/{source.id}/jobs").json()
    assert [item["attempt"] for item in jobs] == [2, 1]
    assert jobs[0]["status"] == "failed"
    assert jobs[1]["error"] == "First attempt failed."

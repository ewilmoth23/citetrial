from __future__ import annotations

import time
from pathlib import Path

import fitz
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core.config import DEFAULT_DATA_DIR, Settings, _find_repository_env, get_settings
from app.core.runtime_settings import effective_settings
from app.ingestion.storage import safe_display_name
from app.models.entities import (
    BriefSection,
    Citation,
    Claim,
    ClaimEvidence,
    ExportedReport,
    Message,
    ModelRun,
    ProcessingJob,
    ProjectActivity,
    ResearchBrief,
    ResearchConversation,
    ResearchNote,
    ResearchProject,
    Source,
    SourceChunk,
    SourceCorrectionRevision,
    SourceDocument,
    SourceDuplicateRelation,
    SourceSection,
    TimelineEvent,
    TimelineEvidence,
)
from app.providers.http import provider_leaves_device


def create_project(client: TestClient, title: str) -> dict:
    response = client.post(
        "/api/v1/projects",
        json={"title": title, "primary_question": "What does the stored evidence show?"},
    )
    assert response.status_code == 201
    return response.json()


def add_note_source(client: TestClient, project_id: str, title: str, content: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/sources/notes",
        json={"title": title, "content": content},
    )
    assert response.status_code == 201
    return response.json()


def pdf_bytes(content: str = "Synthetic PDF evidence.") -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), content)
    data = document.tobytes()
    document.close()
    return data


def paged_pdf_bytes(*pages: str) -> bytes:
    document = fitz.open()
    for content in pages:
        page = document.new_page()
        page.insert_text((72, 72), content)
    data = document.tobytes()
    document.close()
    return data


def wait_for_source_ready(
    client: TestClient,
    project_id: str,
    source_id: str,
    *,
    timeout: float = 5,
) -> dict:
    deadline = time.monotonic() + timeout
    latest: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/projects/{project_id}/sources/{source_id}")
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest["processing_status"] in {"ready", "ready_with_warnings"}:
            return latest
        if latest["processing_status"] == "failed":
            raise AssertionError(latest["error_message"])
        time.sleep(0.02)
    raise AssertionError(f"Source did not become ready: {latest}")


def test_default_data_directory_is_outside_repository() -> None:
    repository = Path(__file__).resolve().parents[3]
    assert not DEFAULT_DATA_DIR.is_relative_to(repository)


def test_repository_env_discovery_handles_shallow_container_install() -> None:
    assert _find_repository_env(Path("/app/app/core/config.py"), Path("/app")) == Path("/app/.env")


def test_windows_and_posix_upload_paths_become_display_only_basenames() -> None:
    assert safe_display_name(r"C:\\private\\report.pdf") == "report.pdf"
    assert safe_display_name("../../private/report.pdf") == "report.pdf"


def test_note_links_cannot_cross_project_boundaries(client: TestClient) -> None:
    first = create_project(client, "First")
    second = create_project(client, "Second")
    foreign_source = add_note_source(client, second["id"], "Foreign", "Foreign evidence.")
    response = client.post(
        f"/api/v1/projects/{first['id']}/notes",
        json={"title": "Bad link", "content": "Note", "source_id": foreign_source["id"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_note_link"


def test_near_duplicate_warning_is_explicitly_heuristic(client: TestClient) -> None:
    project = create_project(client, "Duplicates")
    common = " ".join(f"recorded-evidence-{index}" for index in range(120))
    add_note_source(client, project["id"], "First", f"{common} first-ending")
    second = add_note_source(client, project["id"], "Second", f"{common} second-ending")
    relation = next(
        item for item in second["duplicate_warnings"] if item["duplicate_type"] == "near_duplicate"
    )
    assert relation["similarity"] < 1
    assert "threshold" in relation["reason"].lower()
    assert any("Possible near-duplicate" in warning for warning in second["warnings"])


def test_invalid_and_cross_source_evidence_chunks_are_rejected(client: TestClient) -> None:
    project = create_project(client, "Chunks")
    first = add_note_source(client, project["id"], "First", "Alpha evidence is stored here.")
    second = add_note_source(client, project["id"], "Second", "Beta evidence is stored here.")
    claim = client.post(
        f"/api/v1/projects/{project['id']}/claims", json={"text": "Alpha claim"}
    ).json()
    missing = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/evidence",
        json={
            "source_id": first["id"],
            "source_chunk_id": "00000000-0000-0000-0000-000000000000",
            "excerpt": "Alpha evidence",
            "relationship_type": "supports",
        },
    )
    assert missing.status_code == 422
    beta_result = client.post(
        f"/api/v1/projects/{project['id']}/search",
        json={"query": "Beta evidence", "mode": "lexical", "source_ids": [second["id"]]},
    ).json()["results"][0]
    event = client.post(
        f"/api/v1/projects/{project['id']}/timeline",
        json={
            "title": "Mismatched provenance",
            "date_precision": "unknown",
            "description": "Should fail.",
            "evidence": [
                {
                    "source_id": first["id"],
                    "source_chunk_id": beta_result["chunk_id"],
                    "excerpt": "Beta evidence is stored here.",
                }
            ],
        },
    )
    assert event.status_code == 422
    assert event.json()["error"]["code"] == "invalid_chunk"


def test_model_suggested_timeline_event_cannot_arrive_preaccepted(client: TestClient) -> None:
    project = create_project(client, "Timeline")
    response = client.post(
        f"/api/v1/projects/{project['id']}/timeline",
        json={
            "title": "Suggested event",
            "date_precision": "unknown",
            "description": "Model suggestion.",
            "origin": "model_suggestion",
            "review_status": "accepted",
        },
    )
    assert response.status_code == 422


def test_runtime_provider_settings_survive_fresh_settings_object(client: TestClient, db) -> None:
    response = client.patch(
        "/api/v1/settings",
        json={"values": {"model_name": "audit-model", "model_base_url": "http://[::1]:11434"}},
    )
    assert response.status_code == 200, response.text
    effective = effective_settings(Settings(), db)
    assert effective.model_name == "audit-model"
    assert effective.model_base_url == "http://[::1]:11434"


def test_provider_locality_uses_parsed_hostname() -> None:
    assert provider_leaves_device("http://[::1]:11434") is False
    assert provider_leaves_device("http://192.168.1.20:11434") is False
    assert provider_leaves_device("https://models.example/localhost") is True


def test_source_deletion_removes_file_index_and_evidence(client: TestClient, db) -> None:
    project = create_project(client, "Source cleanup")
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={"file": ("report.pdf", pdf_bytes(), "application/pdf")},
    )
    assert uploaded.status_code == 202, uploaded.text
    source_id = uploaded.json()["id"]
    assert uploaded.json()["processing_job"]["status"] in {"queued", "running"}
    ready = wait_for_source_ready(client, project["id"], source_id)
    assert ready["processing_job"]["status"] == "complete"
    assert ready["processing_job"]["progress"] == 1
    jobs = client.get(f"/api/v1/projects/{project['id']}/sources/{source_id}/jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["attempt"] == 1
    db.expire_all()
    source = db.get(Source, source_id)
    assert source and source.storage_key
    stored_path = get_settings().upload_dir / source.storage_key
    assert stored_path.is_file()
    result = client.post(
        f"/api/v1/projects/{project['id']}/search",
        json={"query": "Synthetic PDF evidence", "mode": "lexical"},
    ).json()["results"][0]
    claim = client.post(
        f"/api/v1/projects/{project['id']}/claims", json={"text": "PDF claim"}
    ).json()
    linked = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/evidence",
        json={
            "source_id": source_id,
            "source_chunk_id": result["chunk_id"],
            "excerpt": "Synthetic PDF evidence.",
            "relationship_type": "supports",
        },
    )
    assert linked.status_code == 201, linked.text
    deleted = client.delete(f"/api/v1/projects/{project['id']}/sources/{source_id}")
    assert deleted.status_code == 204
    db.expire_all()
    assert db.get(Source, source_id) is None
    assert db.scalar(select(func.count()).select_from(SourceDocument)) == 0
    assert db.scalar(select(func.count()).select_from(SourceCorrectionRevision)) == 0
    assert db.scalar(select(func.count()).select_from(SourceSection)) == 0
    assert db.scalar(select(func.count()).select_from(SourceChunk)) == 0
    assert db.scalar(select(func.count()).select_from(ClaimEvidence)) == 0
    assert db.scalar(text("SELECT COUNT(*) FROM source_chunks_fts")) == 0
    assert not stored_path.exists()


def test_pdf_correction_remaps_active_chunks_to_original_pages(client: TestClient) -> None:
    project = create_project(client, "PDF correction lineage")
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={
            "file": (
                "pages.pdf",
                paged_pdf_bytes(
                    "First-page cobalt measurement was 12.5.",
                    "Second-page amber measurement was 44.0.",
                ),
                "application/pdf",
            )
        },
    )
    assert uploaded.status_code == 202, uploaded.text
    source_id = uploaded.json()["id"]
    wait_for_source_ready(client, project["id"], source_id)
    content = client.get(f"/api/v1/projects/{project['id']}/sources/{source_id}/content").json()
    assert content["page_count"] == 2
    corrected_text = content["normalized_text"].replace("12.5", "12.6")
    corrected = client.post(
        f"/api/v1/projects/{project['id']}/sources/{source_id}/correction",
        json={
            "corrected_text": corrected_text,
            "correction_note": "Corrected the first-page decimal after visual review.",
        },
    )
    assert corrected.status_code == 200, corrected.text
    history = client.get(f"/api/v1/projects/{project['id']}/sources/{source_id}/content").json()[
        "correction_history"
    ]
    assert history[0]["location_status"] == "aligned"
    assert history[0]["alignment_confidence"] > 0.95

    first_page = client.post(
        f"/api/v1/projects/{project['id']}/search",
        json={"query": "cobalt 12.6", "mode": "lexical"},
    ).json()["results"]
    second_page = client.post(
        f"/api/v1/projects/{project['id']}/search",
        json={"query": "amber 44.0", "mode": "lexical"},
    ).json()["results"]
    assert first_page and first_page[0]["location"]["page_number"] == 1
    assert second_page and second_page[0]["location"]["page_number"] == 2


def test_project_deletion_cascades_every_project_record(client: TestClient, db) -> None:
    project = create_project(client, "Project cleanup")
    source = add_note_source(client, project["id"], "Evidence", "Stored cleanup evidence.")
    claim = client.post(
        f"/api/v1/projects/{project['id']}/claims", json={"text": "Cleanup claim"}
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/evidence",
        json={
            "source_id": source["id"],
            "excerpt": "Stored cleanup evidence.",
            "relationship_type": "uncertain",
        },
    )
    client.post(
        f"/api/v1/projects/{project['id']}/notes",
        json={"title": "Cleanup note", "content": "User note", "claim_id": claim["id"]},
    )
    client.post(f"/api/v1/projects/{project['id']}/briefs", json={})
    conversation = client.post(f"/api/v1/projects/{project['id']}/conversations", json={}).json()
    client.post(
        f"/api/v1/projects/{project['id']}/conversations/{conversation['id']}/messages",
        json={"question": "What cleanup evidence is stored?", "retrieval_mode": "lexical"},
    )
    client.get(f"/api/v1/projects/{project['id']}/exports/json")
    corrected = client.post(
        f"/api/v1/projects/{project['id']}/sources/{source['id']}/correction",
        json={
            "corrected_text": "Stored reviewed cleanup evidence.",
            "correction_note": "Reviewed before project deletion.",
        },
    )
    assert corrected.status_code == 200, corrected.text
    deleted = client.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 204
    db.expire_all()
    project_models = (
        ResearchProject,
        Source,
        SourceDocument,
        SourceCorrectionRevision,
        SourceSection,
        SourceChunk,
        SourceDuplicateRelation,
        Claim,
        ClaimEvidence,
        ResearchNote,
        TimelineEvent,
        TimelineEvidence,
        ResearchBrief,
        BriefSection,
        ResearchConversation,
        Message,
        Citation,
        ProcessingJob,
        ModelRun,
        ExportedReport,
        ProjectActivity,
    )
    for model in project_models:
        assert db.scalar(select(func.count()).select_from(model)) == 0, model.__name__
    assert db.scalar(text("SELECT COUNT(*) FROM source_chunks_fts")) == 0

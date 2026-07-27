from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.entities import Citation, SourceChunk, SourceCorrectionRevision


def create_project(client: TestClient, title: str = "Transit research") -> dict:
    response = client.post(
        "/api/v1/projects",
        json={"title": title, "primary_question": "What changed after the transit pilot?"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def add_note_source(client: TestClient, project_id: str, title: str = "Report") -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/sources/notes",
        json={
            "title": title,
            "content": "Weekday boardings increased from 6,800 to 8,240 in September.\n\nConstruction may have shifted riders.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_project_lifecycle_and_validation(client: TestClient) -> None:
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["checks"]["ingestion_worker"]["status"] == "healthy"
    assert health.json()["checks"]["data_directory_lock"] == {
        "status": "healthy",
        "mode": "exclusive single-owner",
    }
    invalid = client.post("/api/v1/projects", json={"title": "", "primary_question": "x"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    project = create_project(client)
    assert client.get(f"/api/v1/projects/{project['id']}").json()["source_count"] == 0
    archived = client.post(f"/api/v1/projects/{project['id']}/archive")
    assert archived.json()["status"] == "archived"
    reopened = client.post(f"/api/v1/projects/{project['id']}/reopen")
    assert reopened.json()["status"] == "draft"


def test_note_ingestion_search_is_project_scoped_and_selected_source_filtered(
    client: TestClient,
) -> None:
    first = create_project(client, "First")
    second = create_project(client, "Second")
    source = add_note_source(client, first["id"], "Boarding report")
    add_note_source(client, second["id"], "Private second project")
    response = client.post(
        f"/api/v1/projects/{first['id']}/search",
        json={"query": "8,240 boardings", "mode": "hybrid", "source_ids": [source["id"]]},
    )
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert results
    assert {item["source_id"] for item in results} == {source["id"]}
    assert all(item["source_title"] == "Boarding report" for item in results)


def test_exact_phrase_is_a_hard_retrieval_boundary(client: TestClient) -> None:
    project = create_project(client)
    matching = add_note_source(client, project["id"], "Matching report")
    unrelated = client.post(
        f"/api/v1/projects/{project['id']}/sources/notes",
        json={
            "title": "Unrelated report",
            "content": "Fuel costs increased while service frequency improved.",
        },
    )
    assert unrelated.status_code == 201, unrelated.text

    response = client.post(
        f"/api/v1/projects/{project['id']}/search",
        json={
            "query": "Construction may have shifted riders",
            "mode": "hybrid",
            "phrase": True,
        },
    )
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert results
    assert {item["source_id"] for item in results} == {matching["id"]}
    assert all(item["method"] == "lexical" for item in results)
    assert all(
        "construction may have shifted riders" in item["excerpt"].casefold() for item in results
    )


def test_exact_duplicate_content_is_warned_not_deleted(client: TestClient) -> None:
    project = create_project(client)
    first = add_note_source(client, project["id"], "First copy")
    second = add_note_source(client, project["id"], "Second copy")
    assert first["id"] != second["id"]
    assert any(item["duplicate_type"] == "exact_content" for item in second["duplicate_warnings"])
    listed = client.get(f"/api/v1/projects/{project['id']}/sources").json()
    assert listed["total"] == 2


def test_source_correction_preserves_original_and_rebuilds_search(client: TestClient, db) -> None:
    project = create_project(client)
    source = add_note_source(client, project["id"])
    correction = client.post(
        f"/api/v1/projects/{project['id']}/sources/{source['id']}/correction",
        json={
            "corrected_text": "Corrected weekday boardings were 8,241.",
            "correction_note": "Fixed one transcribed digit after checking the local source.",
        },
    )
    assert correction.status_code == 200, correction.text
    content = client.get(f"/api/v1/projects/{project['id']}/sources/{source['id']}/content").json()
    assert "8,240" in content["raw_text"]
    assert "8,240" in content["normalized_text"]
    assert content["corrected_text"] == "Corrected weekday boardings were 8,241."
    assert content["correction_note"].startswith("Fixed one")
    assert content["correction_revision"] == 1
    assert len(content["correction_history"]) == 1
    assert content["correction_history"][0]["revision"] == 1
    assert content["correction_history"][0]["location_status"] == "reparsed"
    no_op = client.post(
        f"/api/v1/projects/{project['id']}/sources/{source['id']}/correction",
        json={
            "corrected_text": "Corrected weekday boardings were 8,241.",
            "correction_note": "No text change.",
        },
    )
    assert no_op.status_code == 409
    assert no_op.json()["error"]["code"] == "correction_unchanged"
    blank_note = client.post(
        f"/api/v1/projects/{project['id']}/sources/{source['id']}/correction",
        json={
            "corrected_text": "Different searchable text.",
            "correction_note": "   ",
        },
    )
    assert blank_note.status_code == 422
    search = client.post(
        f"/api/v1/projects/{project['id']}/search",
        json={"query": "8,241", "mode": "lexical"},
    ).json()
    assert search["results"]
    removed = client.post(
        f"/api/v1/projects/{project['id']}/search",
        json={"query": "Construction", "mode": "lexical"},
    ).json()
    assert removed["results"] == []

    second = client.post(
        f"/api/v1/projects/{project['id']}/sources/{source['id']}/correction",
        json={
            "corrected_text": "Quartzrevision confirms 8,242 weekday boardings.",
            "correction_note": "Recorded a second reviewed revision.",
        },
    )
    assert second.status_code == 200, second.text
    content = client.get(f"/api/v1/projects/{project['id']}/sources/{source['id']}/content").json()
    assert content["correction_revision"] == 2
    assert [item["revision"] for item in content["correction_history"]] == [1, 2]
    assert content["correction_history"][0]["correction_note"].startswith("Fixed one")
    db.expire_all()
    assert (
        db.scalar(
            select(func.count())
            .select_from(SourceCorrectionRevision)
            .where(SourceCorrectionRevision.source_id == source["id"])
        )
        == 2
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(SourceChunk)
            .where(SourceChunk.source_id == source["id"], SourceChunk.is_active.is_(True))
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(SourceChunk)
            .where(SourceChunk.source_id == source["id"], SourceChunk.is_active.is_(False))
        )
        >= 2
    )


def test_citation_survives_source_correction_and_keeps_revision(client: TestClient, db) -> None:
    project = create_project(client, "Citation lineage")
    response = client.post(
        f"/api/v1/projects/{project['id']}/sources/notes",
        json={
            "title": "Calibration record",
            "content": "The heliotrope baseline measured 7.25 units in the reviewed record.",
        },
    )
    assert response.status_code == 201, response.text
    source = response.json()
    conversation = client.post(
        f"/api/v1/projects/{project['id']}/conversations",
        json={"selected_source_ids": [source["id"]]},
    ).json()
    answer = client.post(
        f"/api/v1/projects/{project['id']}/conversations/{conversation['id']}/messages",
        json={"question": "What was the heliotrope baseline?", "retrieval_mode": "lexical"},
    )
    assert answer.status_code == 200, answer.text
    citation = answer.json()["answer_message"]["citations"][0]
    assert citation["source_revision"] == 0
    original_chunk_id = citation["source_chunk_id"]

    correction = client.post(
        f"/api/v1/projects/{project['id']}/sources/{source['id']}/correction",
        json={
            "corrected_text": "The cerulean baseline measured 7.30 units in the reviewed record.",
            "correction_note": "Replaced the superseded calibration transcription.",
        },
    )
    assert correction.status_code == 200, correction.text

    stored = client.get(
        f"/api/v1/projects/{project['id']}/conversations/{conversation['id']}"
    ).json()
    stored_citation = next(
        item
        for message in stored["messages"]
        for item in message["citations"]
        if item["id"] == citation["id"]
    )
    assert stored_citation["source_chunk_id"] == original_chunk_id
    assert stored_citation["source_revision"] == 0
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Citation)) == 1
    historical_chunk = db.get(SourceChunk, original_chunk_id)
    assert historical_chunk is not None
    assert historical_chunk.is_active is False

    old_search = client.post(
        f"/api/v1/projects/{project['id']}/search",
        json={"query": "heliotrope", "mode": "lexical"},
    ).json()
    new_search = client.post(
        f"/api/v1/projects/{project['id']}/search",
        json={"query": "cerulean", "mode": "lexical"},
    ).json()
    assert old_search["results"] == []
    assert new_search["results"]


def test_claim_evidence_verification_and_contradiction(client: TestClient) -> None:
    project = create_project(client)
    source = add_note_source(client, project["id"])
    claim = client.post(
        f"/api/v1/projects/{project['id']}/claims",
        json={"text": "Boardings increased", "claim_type": "factual"},
    ).json()
    valid = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/evidence",
        json={
            "source_id": source["id"],
            "excerpt": "Weekday boardings increased from 6,800 to 8,240 in September.",
            "relationship_type": "supports",
        },
    )
    assert valid.status_code == 201, valid.text
    assert valid.json()["source_revision"] == 0
    changed = client.patch(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/evidence/{valid.json()['id']}?relationship_type=contradicts"
    )
    assert changed.json()["relationship_type"] == "contradicts"
    correction = client.post(
        f"/api/v1/projects/{project['id']}/sources/{source['id']}/correction",
        json={
            "corrected_text": "Reviewed weekday boardings increased to 8,241 in September.",
            "correction_note": "Corrected the reviewed total.",
        },
    )
    assert correction.status_code == 200, correction.text
    revised = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/evidence",
        json={
            "source_id": source["id"],
            "excerpt": "Reviewed weekday boardings increased to 8,241 in September.",
            "relationship_type": "supports",
        },
    )
    assert revised.status_code == 201, revised.text
    assert revised.json()["source_revision"] == 1
    invalid = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/evidence",
        json={
            "source_id": source["id"],
            "excerpt": "This quotation was invented.",
            "relationship_type": "supports",
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "unmatched_evidence"


def test_timeline_precision_validation(client: TestClient) -> None:
    project = create_project(client)
    source = add_note_source(client, project["id"])
    valid = client.post(
        f"/api/v1/projects/{project['id']}/timeline",
        json={
            "title": "Tuning began",
            "date_label": "around late spring 2032",
            "date_precision": "approximate",
            "description": "No exact day was recorded.",
            "evidence": [
                {
                    "source_id": source["id"],
                    "excerpt": "Construction may have shifted riders.",
                }
            ],
        },
    )
    assert valid.status_code == 201, valid.text
    assert valid.json()["date_start"] is None
    assert valid.json()["evidence"][0]["source_revision"] == 0
    invalid = client.post(
        f"/api/v1/projects/{project['id']}/timeline",
        json={
            "title": "Bad precision",
            "date_precision": "approximate",
            "description": "Missing the original wording.",
            "evidence": [
                {
                    "source_id": source["id"],
                    "excerpt": "Construction may have shifted riders.",
                }
            ],
        },
    )
    assert invalid.status_code == 422


def test_brief_preserves_user_edits_and_exports(client: TestClient) -> None:
    project = create_project(client)
    source = add_note_source(client, project["id"])
    corrected = client.post(
        f"/api/v1/projects/{project['id']}/sources/{source['id']}/correction",
        json={
            "corrected_text": "Reviewed export text records 8,241 weekday boardings.",
            "correction_note": "Reviewed before export.",
        },
    )
    assert corrected.status_code == 200, corrected.text
    brief = client.post(f"/api/v1/projects/{project['id']}/briefs", json={}).json()
    section = next(
        item for item in brief["sections"] if item["section_type"] == "executive_summary"
    )
    edited = client.patch(
        f"/api/v1/projects/{project['id']}/briefs/{brief['id']}/sections/{section['id']}",
        json={"content": "My reviewed summary."},
    )
    assert edited.json()["user_edited"] is True
    blocked = client.post(
        f"/api/v1/projects/{project['id']}/briefs/{brief['id']}/sections/{section['id']}/generate",
        json={"force_replace_user_edit": False},
    )
    assert blocked.status_code == 409
    markdown = client.get(f"/api/v1/projects/{project['id']}/exports/markdown")
    assert markdown.status_code == 200
    assert "# Transit research" in markdown.text
    exported = client.get(f"/api/v1/projects/{project['id']}/exports/json").json()
    assert exported["schema_version"] == "1.1"
    exported_source = exported["sources"][0]
    assert exported_source["correction_revision"] == 1
    assert exported_source["correction_history"][0]["revision"] == 1
    assert "corrected_text" not in exported_source["correction_history"][0]
    assert "storage_key" not in str(exported)
    assert "full_text" not in str(exported)
    full_export = client.get(
        f"/api/v1/projects/{project['id']}/exports/json?include_full_text=true"
    ).json()
    assert (
        full_export["sources"][0]["correction_history"][0]["corrected_text"]
        == "Reviewed export text records 8,241 weekday boardings."
    )


def test_upload_validation_path_safety_and_complete_deletion(client: TestClient) -> None:
    project = create_project(client)
    invalid = client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={"file": ("../report.pdf", b"not a pdf", "application/pdf")},
    )
    assert invalid.status_code == 422
    source = add_note_source(client, project["id"])
    response = client.delete(f"/api/v1/projects/{project['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}/sources/{source['id']}").status_code == 404

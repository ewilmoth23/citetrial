from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import stat
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.data_lock import DataDirectoryInUseError, DataDirectoryLock
from app.db.session import engine
from app.ingestion.storage import StagedUploadDeletion, recover_staged_upload_deletions
from app.models.entities import Source
from app.services import backups as backup_service
from app.services.backups import (
    BACKUP_FORMAT,
    BACKUP_MEDIA_TYPE,
    DATABASE_ARCHIVE_PATH,
    MANIFEST_PATH,
    BackupValidationError,
    restore_workspace_backup,
    validate_workspace_backup,
)


def create_project(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/projects",
        json={
            "title": "Backup verification",
            "primary_question": "Can the full evidence workspace be restored?",
        },
    )
    assert response.status_code == 201
    return response.json()


def wait_for_source(client: TestClient, project_id: str, source_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/projects/{project_id}/sources/{source_id}")
        assert response.status_code == 200
        source = response.json()
        if source["processing_status"] in {"ready", "ready_with_warnings"}:
            return source
        if source["processing_status"] == "failed":
            raise AssertionError(source["error_message"])
        time.sleep(0.02)
    raise AssertionError("Source did not finish processing")


def download_backup(client: TestClient) -> bytes:
    response = client.post(
        "/api/v1/maintenance/backups",
        headers={"X-CiteTrail-Intent": "backup"},
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == BACKUP_MEDIA_TYPE
    assert response.headers["cache-control"] == "no-store"
    assert ".ctbackup" in response.headers["content-disposition"]
    return response.content


def test_backup_requires_explicit_intent_header(client: TestClient) -> None:
    response = client.post("/api/v1/maintenance/backups", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "backup_intent_required"


def test_backup_stages_on_the_destination_filesystem(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    create_project(client)
    temporary_directories: list[Path] = []
    original = backup_service.tempfile.TemporaryDirectory

    def tracked_temporary_directory(*args, **kwargs):
        temporary_directories.append(Path(kwargs["dir"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(
        backup_service.tempfile,
        "TemporaryDirectory",
        tracked_temporary_directory,
    )
    destination = tmp_path / "atomic.ctbackup"
    backup_service.create_workspace_backup(get_settings(), engine, destination)

    assert destination.is_file()
    assert temporary_directories == [tmp_path]


def test_workspace_backup_round_trip_preserves_database_and_upload(
    client: TestClient, tmp_path: Path
) -> None:
    project = create_project(client)
    upload_bytes = b"# Verified record\n\nThe resilient observation is stored locally.\n"
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={"file": ("evidence.md", upload_bytes, "text/markdown")},
    )
    assert uploaded.status_code == 202
    source = wait_for_source(client, project["id"], uploaded.json()["id"])

    archive_path = tmp_path / "workspace.ctbackup"
    archive_path.write_bytes(download_backup(client))
    manifest = validate_workspace_backup(archive_path)
    assert manifest.format == BACKUP_FORMAT
    assert manifest.statistics["projects"] == 1
    assert manifest.statistics["sources"] == 1
    assert DATABASE_ARCHIVE_PATH in {item.path for item in manifest.files}
    assert all(not Path(item.path).is_absolute() for item in manifest.files)

    restored_data = tmp_path / "restored-data"
    result = restore_workspace_backup(archive_path, restored_data)
    assert result.rollback_path is None
    with sqlite3.connect(restored_data / "citetrail.db") as restored:
        restored_project = restored.execute(
            "SELECT title FROM research_projects WHERE id = ?", (project["id"],)
        ).fetchone()
        restored_source = restored.execute(
            "SELECT storage_key, processing_status FROM sources WHERE id = ?",
            (source["id"],),
        ).fetchone()
    assert restored_project == ("Backup verification",)
    assert restored_source is not None
    storage_key, processing_status = restored_source
    assert processing_status in {"ready", "ready_with_warnings"}
    assert (restored_data / "uploads" / storage_key).read_bytes() == upload_bytes


def test_restore_retains_previous_workspace_for_manual_rollback(
    client: TestClient, tmp_path: Path
) -> None:
    create_project(client)
    archive_path = tmp_path / "workspace.ctbackup"
    archive_path.write_bytes(download_backup(client))
    target = tmp_path / "existing"
    target.mkdir()
    (target / "citetrail.db").write_bytes(b"previous workspace sentinel")
    (target / "uploads").mkdir()
    (target / "uploads" / "old.txt").write_text("previous upload", encoding="utf-8")

    result = restore_workspace_backup(archive_path, target)

    assert result.rollback_path is not None
    assert (result.rollback_path / "citetrail.db").read_bytes() == b"previous workspace sentinel"
    assert (result.rollback_path / "uploads" / "old.txt").read_text() == "previous upload"
    with sqlite3.connect(target / "citetrail.db") as restored:
        assert restored.execute("SELECT COUNT(*) FROM research_projects").fetchone()[0] == 1


def test_backup_fails_closed_when_a_referenced_upload_is_missing(client: TestClient, db) -> None:
    project = create_project(client)
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={"file": ("evidence.txt", b"Referenced local evidence.", "text/plain")},
    )
    source = wait_for_source(client, project["id"], uploaded.json()["id"])
    settings = get_settings()
    db.expire_all()
    source_record = db.get(Source, source["id"])
    assert source_record is not None and source_record.storage_key is not None
    (settings.upload_dir / source_record.storage_key).unlink()

    response = client.post(
        "/api/v1/maintenance/backups",
        headers={"X-CiteTrail-Intent": "backup"},
        json={},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "backup_incomplete"
    assert "missing" in response.json()["error"]["message"].lower()


def test_data_directory_allows_only_one_owner(tmp_path: Path) -> None:
    first = DataDirectoryLock(tmp_path)
    second = DataDirectoryLock(tmp_path)
    first.acquire()
    try:
        with pytest.raises(DataDirectoryInUseError):
            second.acquire()
        assert first.is_acquired
        assert not second.is_acquired
    finally:
        first.release()
    second.acquire()
    second.release()


def test_interrupted_precommit_deletion_restores_referenced_upload(client: TestClient, db) -> None:
    project = create_project(client)
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={"file": ("restore.txt", b"Restore after interruption.", "text/plain")},
    )
    wait_for_source(client, project["id"], uploaded.json()["id"])
    db.expire_all()
    source = db.get(Source, uploaded.json()["id"])
    assert source is not None and source.storage_key is not None
    original = get_settings().upload_dir / source.storage_key

    StagedUploadDeletion.stage([source.storage_key], get_settings())
    assert not original.exists()
    restored, finalized = recover_staged_upload_deletions(get_settings(), db)

    assert (restored, finalized) == (1, 0)
    assert original.read_bytes() == b"Restore after interruption."


def test_startup_recovery_finishes_postcommit_upload_deletion(client: TestClient, db) -> None:
    project = create_project(client)
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={"file": ("finalize.txt", b"Finalize after commit.", "text/plain")},
    )
    wait_for_source(client, project["id"], uploaded.json()["id"])
    db.expire_all()
    source = db.get(Source, uploaded.json()["id"])
    assert source is not None and source.storage_key is not None
    storage_key = source.storage_key
    original = get_settings().upload_dir / storage_key

    StagedUploadDeletion.stage([storage_key], get_settings())
    db.delete(source)
    db.commit()
    restored, finalized = recover_staged_upload_deletions(get_settings(), db)

    assert (restored, finalized) == (0, 1)
    assert not original.exists()


def test_source_deletion_database_failure_restores_staged_upload(
    client: TestClient, db, monkeypatch
) -> None:
    project = create_project(client)
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={"file": ("rollback.txt", b"Rollback must retain these bytes.", "text/plain")},
    )
    wait_for_source(client, project["id"], uploaded.json()["id"])
    db.expire_all()
    source = db.get(Source, uploaded.json()["id"])
    assert source is not None and source.storage_key is not None
    original = get_settings().upload_dir / source.storage_key

    def fail_commit(_session: Session) -> None:
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.delete(f"/api/v1/projects/{project['id']}/sources/{uploaded.json()['id']}")
    monkeypatch.undo()

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "deletion_failed"
    db.expire_all()
    assert db.get(Source, uploaded.json()["id"]) is not None
    assert original.read_bytes() == b"Rollback must retain these bytes."


def write_archive(path: Path, entries: list[tuple[zipfile.ZipInfo | str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)


def minimal_manifest(
    database_bytes: bytes,
    *,
    digest: str | None = None,
    schema_revision: str | None = None,
) -> bytes:
    return json.dumps(
        {
            "format": BACKUP_FORMAT,
            "format_version": 1,
            "application_version": "0.1.0",
            "created_at": "2026-07-24T00:00:00Z",
            "schema_revision": schema_revision,
            "database_path": DATABASE_ARCHIVE_PATH,
            "files": [
                {
                    "path": DATABASE_ARCHIVE_PATH,
                    "size": len(database_bytes),
                    "sha256": digest or hashlib.sha256(database_bytes).hexdigest(),
                }
            ],
            "statistics": {},
        }
    ).encode()


@pytest.mark.parametrize("unsafe_name", ["../escape", "/absolute", r"uploads\\escape"])
def test_backup_validator_rejects_unsafe_archive_paths(tmp_path: Path, unsafe_name: str) -> None:
    archive_path = tmp_path / "unsafe.ctbackup"
    write_archive(
        archive_path,
        [
            (unsafe_name, b"unsafe"),
            (MANIFEST_PATH, minimal_manifest(b"database")),
        ],
    )
    with pytest.raises(BackupValidationError, match="path"):
        validate_workspace_backup(archive_path)


def test_backup_validator_rejects_checksum_mismatch(tmp_path: Path) -> None:
    archive_path = tmp_path / "checksum.ctbackup"
    database_bytes = b"not the declared database"
    write_archive(
        archive_path,
        [
            (DATABASE_ARCHIVE_PATH, database_bytes),
            (MANIFEST_PATH, minimal_manifest(database_bytes, digest="0" * 64)),
        ],
    )
    with pytest.raises(BackupValidationError, match="checksum"):
        validate_workspace_backup(archive_path)


def test_backup_validator_rejects_unknown_schema_revision(tmp_path: Path) -> None:
    archive_path = tmp_path / "future-schema.ctbackup"
    database_bytes = b"database"
    write_archive(
        archive_path,
        [
            (DATABASE_ARCHIVE_PATH, database_bytes),
            (
                MANIFEST_PATH,
                minimal_manifest(database_bytes, schema_revision="20990101_future"),
            ),
        ],
    )
    with pytest.raises(BackupValidationError, match="schema revision"):
        validate_workspace_backup(archive_path)


def test_restore_rejects_non_sqlite_database_before_replacing_data(tmp_path: Path) -> None:
    archive_path = tmp_path / "not-sqlite.ctbackup"
    database_bytes = b"not a sqlite workspace"
    write_archive(
        archive_path,
        [
            (DATABASE_ARCHIVE_PATH, database_bytes),
            (MANIFEST_PATH, minimal_manifest(database_bytes)),
        ],
    )
    target = tmp_path / "protected-current-data"
    target.mkdir()
    current_database = target / "citetrail.db"
    current_database.write_bytes(b"current workspace remains")

    with pytest.raises(BackupValidationError, match="SQLite"):
        restore_workspace_backup(archive_path, target)

    assert current_database.read_bytes() == b"current workspace remains"


def test_backup_validator_rejects_symbolic_links(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.ctbackup"
    link = zipfile.ZipInfo("uploads/link.txt")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    write_archive(
        archive_path,
        [
            (link, b"../../private"),
            (DATABASE_ARCHIVE_PATH, b"database"),
            (MANIFEST_PATH, minimal_manifest(b"database")),
        ],
    )
    with pytest.raises(BackupValidationError, match="symbolic link"):
        validate_workspace_backup(archive_path)


def test_backup_validator_rejects_undeclared_files(tmp_path: Path) -> None:
    archive_path = tmp_path / "undeclared.ctbackup"
    database_bytes = b"database"
    write_archive(
        archive_path,
        [
            (DATABASE_ARCHIVE_PATH, database_bytes),
            ("uploads/undeclared.txt", b"hidden"),
            (MANIFEST_PATH, minimal_manifest(database_bytes)),
        ],
    )
    with pytest.raises(BackupValidationError, match="exactly match"):
        validate_workspace_backup(archive_path)


def test_downloaded_backup_is_a_regular_zip(client: TestClient) -> None:
    create_project(client)
    with zipfile.ZipFile(io.BytesIO(download_backup(client))) as archive:
        assert MANIFEST_PATH in archive.namelist()

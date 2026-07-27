from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import IO, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.engine import Engine

from app import __version__
from app.core.config import Settings
from app.core.data_lock import DataDirectoryLock

BACKUP_FORMAT = "citetrail-workspace-backup"
BACKUP_FORMAT_VERSION = 1
BACKUP_MEDIA_TYPE = "application/vnd.citetrail.backup+zip"
MANIFEST_PATH = "manifest.json"
DATABASE_ARCHIVE_PATH = "database/citetrail.db"
MAX_BACKUP_FILES = 100_000
MAX_BACKUP_UNCOMPRESSED_BYTES = 100 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
COPY_BUFFER_BYTES = 1024 * 1024
SUPPORTED_SCHEMA_REVISIONS = {
    None,
    "20260718_0001",
    "20260718_0002",
    "20260723_0003",
}


class BackupError(RuntimeError):
    """Raised when a complete workspace backup cannot be created."""


class BackupValidationError(BackupError):
    """Raised when a backup archive is malformed, unsafe, or corrupt."""


class BackupFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=1000)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        _validate_archive_path(value)
        if value == DATABASE_ARCHIVE_PATH:
            return value
        parts = PurePosixPath(value).parts
        if not parts or parts[0] not in {"uploads", "vectors"}:
            raise ValueError("Backup files must be stored under database, uploads, or vectors")
        if parts[0] == "uploads" and len(parts) != 2:
            raise ValueError("Upload backup paths must contain exactly one generated storage key")
        return value


class BackupManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["citetrail-workspace-backup"]
    format_version: Literal[1]
    application_version: str = Field(min_length=1, max_length=80)
    created_at: datetime
    schema_revision: str | None = Field(default=None, max_length=160)
    database_path: Literal["database/citetrail.db"]
    files: list[BackupFile] = Field(max_length=MAX_BACKUP_FILES)
    statistics: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_file_set(self) -> BackupManifest:
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("Backup manifest contains duplicate file paths")
        if paths.count(self.database_path) != 1:
            raise ValueError("Backup manifest must contain exactly one database snapshot")
        if any(value < 0 for value in self.statistics.values()):
            raise ValueError("Backup statistics cannot be negative")
        return self


class RestoreResult(BaseModel):
    manifest: BackupManifest
    rollback_path: Path | None


def backup_filename(created_at: datetime | None = None) -> str:
    timestamp = (created_at or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"citetrail-backup-{timestamp}.ctbackup"


def _validate_archive_path(value: str) -> None:
    if not value or "\\" in value or "\x00" in value:
        raise ValueError("Backup archive path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Backup archive path is not safely relative")


def _copy_and_hash(source: IO[bytes], destination: IO[bytes]) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(COPY_BUFFER_BYTES):
        destination.write(chunk)
        digest.update(chunk)
        size += len(chunk)
    return size, digest.hexdigest()


def _write_archive_file(
    archive: zipfile.ZipFile,
    source_path: Path,
    archive_path: str,
) -> BackupFile:
    info = zipfile.ZipInfo(archive_path, date_time=datetime.now().timetuple()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    with source_path.open("rb") as source, archive.open(info, "w") as destination:
        size, digest = _copy_and_hash(source, destination)
    return BackupFile(path=archive_path, size=size, sha256=digest)


def _snapshot_database(engine: Engine, destination: Path) -> None:
    if engine.dialect.name != "sqlite":
        raise BackupError("Workspace backups currently require the supported SQLite database")
    raw = engine.raw_connection()
    target = sqlite3.connect(destination)
    try:
        driver = cast(sqlite3.Connection, raw.driver_connection)
        driver.backup(target)
        result = target.execute("PRAGMA quick_check").fetchone()
        if result is None or result[0] != "ok":
            raise BackupError("The SQLite snapshot did not pass its integrity check")
    finally:
        target.close()
        raw.close()
    destination.chmod(0o600)


def _snapshot_metadata(database_path: Path) -> tuple[list[str], str | None, dict[str, int]]:
    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        required = {"research_projects", "sources", "source_documents", "source_chunks"}
        if not required.issubset(tables):
            raise BackupError("The database snapshot is missing required CiteTrail tables")
        storage_keys = [
            row[0]
            for row in connection.execute(
                "SELECT storage_key FROM sources WHERE storage_key IS NOT NULL ORDER BY storage_key"
            ).fetchall()
        ]
        schema_revision = None
        if "alembic_version" in tables:
            row = connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
            schema_revision = str(row[0]) if row else None
        statistics = {
            "projects": int(
                connection.execute("SELECT COUNT(*) FROM research_projects").fetchone()[0]
            ),
            "sources": int(connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]),
            "claims": int(connection.execute("SELECT COUNT(*) FROM claims").fetchone()[0]),
            "notes": int(connection.execute("SELECT COUNT(*) FROM research_notes").fetchone()[0]),
        }
        return storage_keys, schema_revision, statistics
    finally:
        connection.close()


def _referenced_uploads(storage_keys: list[str], settings: Settings) -> Iterator[tuple[Path, str]]:
    if settings.upload_dir.is_symlink():
        raise BackupError("The upload data directory cannot be a symbolic link")
    upload_root = settings.upload_dir.resolve()
    for storage_key in storage_keys:
        if storage_key != Path(storage_key).name or "\\" in storage_key:
            raise BackupError("The database contains an invalid upload storage key")
        path = (upload_root / storage_key).resolve()
        if path.parent != upload_root or path.is_symlink():
            raise BackupError("A stored upload resolved outside the protected upload directory")
        if not path.is_file():
            raise BackupError(f"A referenced upload is missing: {storage_key}")
        yield path, f"uploads/{storage_key}"


def _vector_files(settings: Settings) -> Iterator[tuple[Path, str]]:
    if settings.vector_dir.is_symlink():
        raise BackupError("The vector data directory cannot be a symbolic link")
    vector_root = settings.vector_dir.resolve()
    if not vector_root.exists():
        return
    for path in sorted(vector_root.rglob("*")):
        if path.is_symlink():
            raise BackupError("Symbolic links are not allowed in the vector data directory")
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(vector_root):
            raise BackupError("A vector file resolved outside the protected vector directory")
        relative = resolved.relative_to(vector_root).as_posix()
        yield resolved, f"vectors/{relative}"


def create_workspace_backup(
    settings: Settings,
    engine: Engine,
    destination: Path,
) -> BackupManifest:
    """Create a verified SQLite snapshot plus every referenced local data file."""
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists():
        raise BackupError(f"Refusing to overwrite an existing backup: {destination}")

    with tempfile.TemporaryDirectory(
        prefix=".citetrail-backup-build-",
        dir=destination.parent,
    ) as temporary:
        temporary_path = Path(temporary)
        database_snapshot = temporary_path / "citetrail.db"
        pending_archive = temporary_path / "workspace.ctbackup"
        _snapshot_database(engine, database_snapshot)
        storage_keys, schema_revision, statistics = _snapshot_metadata(database_snapshot)

        files: list[BackupFile] = []
        with zipfile.ZipFile(
            pending_archive,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            files.append(_write_archive_file(archive, database_snapshot, DATABASE_ARCHIVE_PATH))
            for source_path, archive_path in _referenced_uploads(storage_keys, settings):
                files.append(_write_archive_file(archive, source_path, archive_path))
            for source_path, archive_path in _vector_files(settings):
                files.append(_write_archive_file(archive, source_path, archive_path))

            manifest = BackupManifest(
                format=BACKUP_FORMAT,
                format_version=BACKUP_FORMAT_VERSION,
                application_version=__version__,
                created_at=datetime.now(UTC),
                schema_revision=schema_revision,
                database_path=DATABASE_ARCHIVE_PATH,
                files=files,
                statistics=statistics,
            )
            manifest_info = zipfile.ZipInfo(
                MANIFEST_PATH, date_time=manifest.created_at.timetuple()[:6]
            )
            manifest_info.compress_type = zipfile.ZIP_DEFLATED
            manifest_info.external_attr = 0o600 << 16
            archive.writestr(
                manifest_info,
                manifest.model_dump_json(indent=2).encode("utf-8"),
            )

        with pending_archive.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(pending_archive, destination)
        destination.chmod(0o600)
        return manifest


def _safe_zip_infos(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if not infos or len(infos) > MAX_BACKUP_FILES + 1:
        raise BackupValidationError("Backup archive file count is invalid")
    by_name: dict[str, zipfile.ZipInfo] = {}
    total_size = 0
    for info in infos:
        try:
            _validate_archive_path(info.filename)
        except ValueError as exc:
            raise BackupValidationError(str(exc)) from exc
        if info.filename in by_name:
            raise BackupValidationError("Backup archive contains duplicate file names")
        if info.is_dir() or info.flag_bits & 0x1:
            raise BackupValidationError("Backup archive contains a directory or encrypted entry")
        unix_mode = info.external_attr >> 16
        if unix_mode and stat.S_ISLNK(unix_mode):
            raise BackupValidationError("Backup archive contains a symbolic link")
        total_size += info.file_size
        if total_size > MAX_BACKUP_UNCOMPRESSED_BYTES:
            raise BackupValidationError("Backup archive expands beyond the safety limit")
        by_name[info.filename] = info
    return by_name


def validate_workspace_backup(archive_path: Path) -> BackupManifest:
    """Validate structure, declared files, sizes, CRC values, and SHA-256 digests."""
    archive_path = archive_path.expanduser().resolve()
    try:
        archive = zipfile.ZipFile(archive_path)
    except (FileNotFoundError, zipfile.BadZipFile, OSError) as exc:
        raise BackupValidationError("Backup is not a readable ZIP archive") from exc

    with archive:
        infos = _safe_zip_infos(archive)
        manifest_info = infos.get(MANIFEST_PATH)
        if manifest_info is None or manifest_info.file_size > MAX_MANIFEST_BYTES:
            raise BackupValidationError("Backup manifest is missing or too large")
        try:
            manifest = BackupManifest.model_validate_json(archive.read(manifest_info))
        except Exception as exc:
            raise BackupValidationError("Backup manifest is invalid") from exc
        if manifest.schema_revision not in SUPPORTED_SCHEMA_REVISIONS:
            raise BackupValidationError(
                "Backup uses a newer or unsupported database schema revision"
            )

        declared = {item.path: item for item in manifest.files}
        if set(infos) != {MANIFEST_PATH, *declared}:
            raise BackupValidationError("Backup files do not exactly match the manifest")
        for path, expected in declared.items():
            info = infos[path]
            if info.file_size != expected.size:
                raise BackupValidationError(f"Backup file size does not match its manifest: {path}")
            digest = hashlib.sha256()
            size = 0
            try:
                with archive.open(info) as source:
                    while chunk := source.read(COPY_BUFFER_BYTES):
                        digest.update(chunk)
                        size += len(chunk)
                        if size > expected.size:
                            raise BackupValidationError(
                                f"Backup file expands beyond its declared size: {path}"
                            )
            except (zipfile.BadZipFile, OSError, EOFError) as exc:
                raise BackupValidationError(f"Backup file is corrupt: {path}") from exc
            if size != expected.size or digest.hexdigest() != expected.sha256:
                raise BackupValidationError(f"Backup checksum mismatch: {path}")
        return manifest


def _extract_validated_backup(
    archive_path: Path,
    manifest: BackupManifest,
    destination: Path,
) -> None:
    declared = {item.path: item for item in manifest.files}
    with zipfile.ZipFile(archive_path) as archive:
        for archive_path_value, expected in declared.items():
            target = destination.joinpath(*PurePosixPath(archive_path_value).parts)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with archive.open(archive_path_value) as source, target.open("xb") as output:
                size, digest = _copy_and_hash(source, output)
                output.flush()
                os.fsync(output.fileno())
            target.chmod(0o600)
            if size != expected.size or digest != expected.sha256:
                raise BackupValidationError(
                    f"Backup changed while it was being restored: {archive_path_value}"
                )


def _validate_restored_database(
    database_path: Path,
    expected_schema_revision: str | None,
) -> None:
    try:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()
            if result is None or result[0] != "ok":
                raise BackupValidationError("Restored database failed its SQLite integrity check")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            required = {"research_projects", "sources", "source_documents", "source_chunks"}
            if not required.issubset(tables):
                raise BackupValidationError("Restored database is not a CiteTrail workspace")
            actual_schema_revision = None
            if "alembic_version" in tables:
                row = connection.execute(
                    "SELECT version_num FROM alembic_version LIMIT 1"
                ).fetchone()
                actual_schema_revision = str(row[0]) if row else None
            if actual_schema_revision != expected_schema_revision:
                raise BackupValidationError(
                    "Restored database schema does not match the backup manifest"
                )
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise BackupValidationError("Restored database is not valid SQLite") from exc


def _move_if_present(source: Path, destination: Path) -> bool:
    if not source.exists() and not source.is_symlink():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.replace(source, destination)
    return True


def restore_workspace_backup(archive_path: Path, target_data_dir: Path) -> RestoreResult:
    """Restore a validated backup while retaining the previous workspace for rollback."""
    archive_path = archive_path.expanduser().resolve()
    target_data_dir = target_data_dir.expanduser().resolve()
    manifest = validate_workspace_backup(archive_path)
    target_data_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target_data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    with DataDirectoryLock(target_data_dir):
        stage_root = Path(
            tempfile.mkdtemp(
                prefix=f".{target_data_dir.name}-restore-stage-",
                dir=target_data_dir.parent,
            )
        )
        rollback_root = target_data_dir.parent / (
            f".{target_data_dir.name}-pre-restore-"
            f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        )
        moved_to_rollback: list[str] = []
        installed: list[str] = []
        try:
            _extract_validated_backup(archive_path, manifest, stage_root)
            staged_database = stage_root / DATABASE_ARCHIVE_PATH
            _validate_restored_database(staged_database, manifest.schema_revision)
            (stage_root / "uploads").mkdir(exist_ok=True, mode=0o700)
            (stage_root / "vectors").mkdir(exist_ok=True, mode=0o700)

            rollback_root.mkdir(mode=0o700)
            for name in (
                "citetrail.db",
                "citetrail.db-wal",
                "citetrail.db-shm",
                "uploads",
                "vectors",
                ".deletion-staging",
            ):
                if _move_if_present(target_data_dir / name, rollback_root / name):
                    moved_to_rollback.append(name)

            replacements = {
                "citetrail.db": staged_database,
                "uploads": stage_root / "uploads",
                "vectors": stage_root / "vectors",
            }
            for name, source in replacements.items():
                os.replace(source, target_data_dir / name)
                installed.append(name)
        except Exception:
            for name in reversed(installed):
                failed_target = target_data_dir / name
                if failed_target.is_dir():
                    shutil.rmtree(failed_target, ignore_errors=True)
                else:
                    failed_target.unlink(missing_ok=True)
            for name in reversed(moved_to_rollback):
                os.replace(rollback_root / name, target_data_dir / name)
            if rollback_root.exists():
                shutil.rmtree(rollback_root, ignore_errors=True)
            raise
        finally:
            shutil.rmtree(stage_root, ignore_errors=True)

        if not moved_to_rollback:
            rollback_root.rmdir()
            retained_rollback: Path | None = None
        else:
            retained_rollback = rollback_root
        return RestoreResult(manifest=manifest, rollback_path=retained_rollback)

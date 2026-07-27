from __future__ import annotations

import os
import shutil
import uuid
from contextlib import suppress
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.entities import Source


class StorageError(RuntimeError):
    pass


ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}
DELETION_STAGING_DIR = ".deletion-staging"


def safe_display_name(original_name: str) -> str:
    """Return a display-only basename for POSIX or Windows-style client paths."""
    cleaned = original_name.replace("\\", "/").replace("\x00", "")
    cleaned = "".join(char for char in cleaned if ord(char) >= 32)
    name = Path(cleaned).name.strip()
    return name[:500] or "source"


def validate_upload(original_name: str, data: bytes, settings: Settings) -> str:
    if not original_name or "\x00" in original_name:
        raise StorageError("Upload filename is invalid")
    suffix = Path(safe_display_name(original_name)).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise StorageError("Only PDF, Markdown, and plain-text uploads are supported")
    if not data:
        raise StorageError("Uploaded file is empty")
    if len(data) > settings.max_upload_bytes:
        raise StorageError("Uploaded file exceeds the configured size limit")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise StorageError("File extension says PDF but its content is not a PDF")
    if suffix != ".pdf" and data.startswith(b"%PDF-"):
        raise StorageError("PDF content must use a .pdf filename")
    return suffix


def persist_upload(original_name: str, data: bytes, settings: Settings) -> str:
    suffix = validate_upload(original_name, data, settings)
    key = f"{uuid.uuid4().hex}{suffix}"
    target = (settings.upload_dir / key).resolve()
    if target.parent != settings.upload_dir.resolve():
        raise StorageError("Resolved upload path escaped the data directory")
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
    return key


def read_upload(storage_key: str, settings: Settings) -> bytes:
    if not storage_key or storage_key != Path(storage_key).name:
        raise StorageError("Invalid storage key")
    target = (settings.upload_dir / storage_key).resolve()
    if target.parent != settings.upload_dir.resolve():
        raise StorageError("Resolved upload path escaped the data directory")
    try:
        return target.read_bytes()
    except FileNotFoundError as exc:
        raise StorageError("Stored source file is missing") from exc


def _validated_upload_path(storage_key: str, settings: Settings) -> Path:
    if not storage_key or storage_key != Path(storage_key).name or "\\" in storage_key:
        raise StorageError("Invalid storage key")
    target = (settings.upload_dir / storage_key).resolve()
    if target.parent != settings.upload_dir.resolve():
        raise StorageError("Resolved upload path escaped the data directory")
    return target


class StagedUploadDeletion:
    """Move uploads aside so database deletion can commit before bytes are destroyed."""

    def __init__(self, transaction_dir: Path, moved: list[tuple[Path, Path]]) -> None:
        self.transaction_dir = transaction_dir
        self.moved = moved

    @classmethod
    def stage(
        cls,
        storage_keys: list[str | None],
        settings: Settings,
    ) -> StagedUploadDeletion:
        staging_root = settings.data_dir / DELETION_STAGING_DIR
        if staging_root.is_symlink():
            raise StorageError("Deletion staging path cannot be a symbolic link")
        staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        transaction_dir = staging_root / uuid.uuid4().hex
        transaction_dir.mkdir(mode=0o700)
        moved: list[tuple[Path, Path]] = []
        try:
            for storage_key in sorted({key for key in storage_keys if key}):
                source = _validated_upload_path(storage_key, settings)
                if not source.exists():
                    continue
                if source.is_symlink() or not source.is_file():
                    raise StorageError("Stored upload is not a regular file")
                staged = transaction_dir / storage_key
                os.replace(source, staged)
                moved.append((source, staged))
        except Exception:
            for source, staged in reversed(moved):
                if staged.exists():
                    os.replace(staged, source)
            shutil.rmtree(transaction_dir, ignore_errors=True)
            raise
        return cls(transaction_dir, moved)

    def restore(self) -> None:
        for source, staged in reversed(self.moved):
            if not staged.exists():
                continue
            if source.exists():
                raise StorageError("Cannot restore a staged upload because its destination exists")
            os.replace(staged, source)
        shutil.rmtree(self.transaction_dir, ignore_errors=True)
        with suppress(OSError):
            self.transaction_dir.parent.rmdir()

    def finalize(self) -> None:
        shutil.rmtree(self.transaction_dir)
        with suppress(OSError):
            self.transaction_dir.parent.rmdir()


def recover_staged_upload_deletions(settings: Settings, db: Session) -> tuple[int, int]:
    """Finish committed deletions and undo interrupted pre-commit deletion stages."""
    staging_root = settings.data_dir / DELETION_STAGING_DIR
    if not staging_root.exists():
        return 0, 0
    if staging_root.is_symlink() or not staging_root.is_dir():
        raise StorageError("Deletion staging path is not a protected directory")

    referenced = set(
        db.scalars(select(Source.storage_key).where(Source.storage_key.is_not(None))).all()
    )
    restored = 0
    finalized = 0
    for transaction_dir in sorted(staging_root.iterdir()):
        if transaction_dir.is_symlink() or not transaction_dir.is_dir():
            raise StorageError("Deletion staging contains an unexpected entry")
        for staged in sorted(transaction_dir.iterdir()):
            if staged.is_symlink() or not staged.is_file() or staged.name != Path(staged.name).name:
                raise StorageError("Deletion staging contains an unsafe upload entry")
            original = _validated_upload_path(staged.name, settings)
            if staged.name in referenced:
                if original.exists():
                    raise StorageError("A staged upload conflicts with an existing referenced file")
                os.replace(staged, original)
                restored += 1
            else:
                staged.unlink()
                finalized += 1
        transaction_dir.rmdir()
    with suppress(OSError):
        staging_root.rmdir()
    return restored, finalized

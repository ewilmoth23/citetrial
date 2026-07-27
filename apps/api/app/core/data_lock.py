from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, BinaryIO, cast


class DataDirectoryInUseError(RuntimeError):
    """Raised when another CiteTrail process owns the data directory."""


class DataDirectoryLock:
    """Hold a cross-platform advisory lock for one CiteTrail data directory."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / ".citetrail.lock"
        self._handle: BinaryIO | None = None

    @property
    def is_acquired(self) -> bool:
        return self._handle is not None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags, 0o600)
            handle = os.fdopen(descriptor, "r+b")
            self._lock(handle)
            handle.seek(0)
            handle.truncate()
            metadata = {
                "pid": os.getpid(),
                "acquired_at": datetime.now(UTC).isoformat(),
            }
            handle.write(json.dumps(metadata, separators=(",", ":")).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        except OSError as exc:
            if "handle" in locals():
                handle.close()
            raise DataDirectoryInUseError(
                f"CiteTrail data directory cannot be exclusively locked: {self.path.parent}"
            ) from exc
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            self._unlock(handle)
        finally:
            handle.close()
            self._handle = None

    @staticmethod
    def _lock(handle: BinaryIO) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if not handle.read(1):
                handle.seek(0)
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt_runtime = cast(Any, msvcrt)
            msvcrt_runtime.locking(handle.fileno(), msvcrt_runtime.LK_NBLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock(handle: BinaryIO) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt_runtime = cast(Any, msvcrt)
            msvcrt_runtime.locking(handle.fileno(), msvcrt_runtime.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def __enter__(self) -> DataDirectoryLock:
        self.acquire()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.release()

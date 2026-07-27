from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

repository = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repository / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.core.data_lock import DataDirectoryInUseError, DataDirectoryLock  # noqa: E402

target = Path(os.environ.get("CITETRAIL_DATA_DIR", get_settings().data_dir)).expanduser().resolve()
if target in {Path("/"), Path.home(), repository} or len(target.parts) < 3:
    raise SystemExit(f"Refusing to reset unsafe data path: {target}")
confirmation = input(f"Delete all local CiteTrail data under {target}? Type RESET: ")
if confirmation != "RESET":
    raise SystemExit("Reset cancelled")
lock = DataDirectoryLock(target)
try:
    lock.acquire()
except DataDirectoryInUseError as exc:
    raise SystemExit(f"Reset refused: {exc}") from exc
try:
    for child in target.iterdir():
        if child == lock.path:
            continue
        if child.is_symlink() or not child.is_dir():
            child.unlink(missing_ok=True)
        else:
            shutil.rmtree(child)
finally:
    lock.release()
lock.path.unlink(missing_ok=True)
target.rmdir()
print(f"Removed {target}. The application will recreate it on next start.")

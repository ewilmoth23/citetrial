from __future__ import annotations

import argparse
from pathlib import Path

from app.core.config import get_settings
from app.core.data_lock import DataDirectoryInUseError
from app.services.backups import (
    BackupValidationError,
    restore_workspace_backup,
    validate_workspace_backup,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and restore a CiteTrail workspace backup. Stop CiteTrail before restoring."
        )
    )
    parser.add_argument("archive", type=Path, help="Path to the .ctbackup archive.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Target data directory. Defaults to the configured CITETRAIL_DATA_DIR.",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Validate and describe the backup without changing any data.",
    )
    parser.add_argument(
        "--confirm",
        choices=["REPLACE"],
        help="Required for restore. Confirms replacement of the current workspace.",
    )
    args = parser.parse_args()

    try:
        manifest = validate_workspace_backup(args.archive)
    except BackupValidationError as exc:
        parser.exit(1, f"Backup validation failed: {exc}\n")

    print(
        f"Valid CiteTrail backup from {manifest.created_at.isoformat()} with "
        f"{manifest.statistics.get('projects', 0)} projects, "
        f"{manifest.statistics.get('sources', 0)} sources, and "
        f"{len(manifest.files)} verified files."
    )
    if args.inspect:
        return
    if args.confirm != "REPLACE":
        parser.exit(
            2,
            "Restore not started. Re-run with --confirm REPLACE after stopping CiteTrail.\n",
        )

    target = (args.data_dir or get_settings().data_dir).expanduser().resolve()
    try:
        result = restore_workspace_backup(args.archive, target)
    except (BackupValidationError, DataDirectoryInUseError, OSError) as exc:
        parser.exit(1, f"Restore failed without replacing the current workspace: {exc}\n")

    print(f"Workspace restored to {target}")
    if result.rollback_path is not None:
        print(f"The previous workspace was retained at {result.rollback_path}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path

from app.core.config import get_settings
from app.core.data_lock import DataDirectoryInUseError, DataDirectoryLock
from app.services.backups import BackupError, backup_filename, create_workspace_backup


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an offline, verified CiteTrail workspace backup."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd() / backup_filename(),
        help="Destination .ctbackup file (must not already exist).",
    )
    args = parser.parse_args()
    settings = get_settings()

    try:
        with DataDirectoryLock(settings.data_dir):
            from app.db.session import engine

            manifest = create_workspace_backup(settings, engine, args.output)
    except (BackupError, DataDirectoryInUseError) as exc:
        parser.exit(1, f"Backup failed: {exc}\n")

    print(f"Backup written to {args.output.expanduser().resolve()}")
    print(
        f"Verified {len(manifest.files)} files for "
        f"{manifest.statistics.get('projects', 0)} projects and "
        f"{manifest.statistics.get('sources', 0)} sources."
    )


if __name__ == "__main__":
    main()

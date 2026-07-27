"""Make ingestion jobs durable and restart recoverable.

Revision ID: 20260723_0003
Revises: 20260718_0002
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260723_0003"
down_revision = "20260718_0002"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    columns = _column_names("processing_jobs")
    additions = (
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("recovery_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default="1970-01-01 00:00:00.000000",
        ),
    )
    for column in additions:
        if column.name not in columns:
            op.add_column("processing_jobs", column)

    # Older versions could leave committed "running" rows after a failed webpage
    # attempt. Retire them before enforcing one active job per source; startup
    # recovery reconstructs work only for sources still in a nonterminal state.
    op.execute(
        """
        UPDATE processing_jobs
        SET status = 'interrupted',
            stage = 'interrupted',
            completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)
        WHERE status IN ('queued', 'running')
        """
    )

    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("processing_jobs")}
    if "uq_processing_jobs_active_source" not in indexes:
        op.create_index(
            "uq_processing_jobs_active_source",
            "processing_jobs",
            ["source_id"],
            unique=True,
            sqlite_where=sa.text("status IN ('queued', 'running')"),
        )


def downgrade() -> None:
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("processing_jobs")}
    if "uq_processing_jobs_active_source" in indexes:
        op.drop_index(
            "uq_processing_jobs_active_source",
            table_name="processing_jobs",
        )
    for column_name in ("created_at", "recovery_count", "attempt"):
        if column_name in _column_names("processing_jobs"):
            op.drop_column("processing_jobs", column_name)

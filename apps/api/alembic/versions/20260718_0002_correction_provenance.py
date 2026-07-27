"""Preserve correction revisions and historical chunks.

Revision ID: 20260718_0002
Revises: 20260718_0001
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260718_0002"
down_revision = "20260718_0001"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "source_correction_revisions" not in tables:
        op.create_table(
            "source_correction_revisions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("source_id", sa.String(length=36), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("corrected_text", sa.Text(), nullable=False),
            sa.Column("correction_note", sa.Text(), nullable=False),
            sa.Column("previous_text_hash", sa.String(length=64), nullable=False),
            sa.Column("corrected_text_hash", sa.String(length=64), nullable=False),
            sa.Column("alignment_method", sa.String(length=80), nullable=False),
            sa.Column("alignment_confidence", sa.Float(), nullable=False),
            sa.Column("location_status", sa.String(length=30), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_id", "revision", name="uq_source_correction_revision"),
        )
        op.create_index(
            "ix_source_correction_revisions_source_id",
            "source_correction_revisions",
            ["source_id"],
        )

    additions = {
        "source_documents": sa.Column(
            "correction_revision", sa.Integer(), nullable=False, server_default="0"
        ),
        "source_chunks": sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        "claim_evidence": sa.Column(
            "source_revision", sa.Integer(), nullable=False, server_default="0"
        ),
        "timeline_evidence": sa.Column(
            "source_revision", sa.Integer(), nullable=False, server_default="0"
        ),
        "citations": sa.Column("source_revision", sa.Integer(), nullable=False, server_default="0"),
    }
    for table_name, column in additions.items():
        if column.name not in _column_names(table_name):
            op.add_column(table_name, column)

    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("source_chunks")}
    if "ix_source_chunks_is_active" not in indexes:
        op.create_index("ix_source_chunks_is_active", "source_chunks", ["is_active"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("source_chunks")}
    if "ix_source_chunks_is_active" in indexes:
        op.drop_index("ix_source_chunks_is_active", table_name="source_chunks")
    for table_name, column_name in (
        ("citations", "source_revision"),
        ("timeline_evidence", "source_revision"),
        ("claim_evidence", "source_revision"),
        ("source_chunks", "is_active"),
        ("source_documents", "correction_revision"),
    ):
        if column_name in _column_names(table_name):
            op.drop_column(table_name, column_name)
    if "source_correction_revisions" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("source_correction_revisions")

"""Initial provenance-first schema.

Revision ID: 20260718_0001
Revises:
"""

from alembic import op
from app.db.base import Base
from app.models import entities  # noqa: F401

revision = "20260718_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS source_chunks_fts USING fts5(
            chunk_id UNINDEXED,
            project_id UNINDEXED,
            source_id UNINDEXED,
            content,
            tokenize='porter unicode61'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_chunks_fts")
    Base.metadata.drop_all(bind=op.get_bind())

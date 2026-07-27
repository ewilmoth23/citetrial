from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
from app.models import entities  # noqa: F401


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            connection.execute(
                text(
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
            )

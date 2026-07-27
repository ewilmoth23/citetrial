from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

TEST_DATA = Path(tempfile.gettempdir()) / f"citetrail-pytest-{os.getpid()}"
os.environ["CITETRAIL_DATA_DIR"] = str(TEST_DATA)
os.environ["CITETRAIL_MODEL_TIMEOUT_SECONDS"] = "0.1"

from app.db.base import Base  # noqa: E402
from app.db.init_db import init_database  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS source_chunks_fts"))
    Base.metadata.drop_all(bind=engine)
    init_database()
    yield


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def pytest_sessionfinish() -> None:
    engine.dispose()
    shutil.rmtree(TEST_DATA, ignore_errors=True)

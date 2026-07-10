"""Test fixtures: fresh temp SQLite DB, auth disabled."""
import os
import tempfile

# Configure the app BEFORE importing anything that reads settings.
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["API_KEYS"] = ""  # disable auth for tests
os.environ["VALID_MATCH_STATUSES"] = "VALID,ACTIVE"

import pytest
from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    init_db()
    yield
    try:
        os.remove(_db_path)
    except OSError:
        pass


@pytest.fixture()
def client():
    return TestClient(app)

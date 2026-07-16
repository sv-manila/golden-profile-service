"""Test fixtures: fresh temp SQLite DB, auth disabled."""
import os
import tempfile

# Configure the app BEFORE importing anything that reads settings.
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["API_KEYS"] = ""  # disable auth for tests
os.environ["VALID_MATCH_STATUSES"] = "VALID,ACTIVE"

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.streamline_schema import credential_matches, employees


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


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def seed_employee(db, **kwargs):
    """Insert one employees row; returns its id. Unset columns default to
    NULL/None — callers pass only the columns their test cares about.

    `date_of_birth` may be passed as an ISO string ("1990-05-05") for
    readability — SQLite's Date column only accepts `datetime.date` objects,
    so it's coerced here rather than at every call site."""
    kwargs.setdefault("terminated", False)
    dob = kwargs.get("date_of_birth")
    if isinstance(dob, str):
        kwargs["date_of_birth"] = date.fromisoformat(dob)
    result = db.execute(employees.insert().values(**kwargs))
    db.commit()
    return kwargs.get("id") or result.inserted_primary_key[0]


def seed_credential_match(db, **kwargs):
    kwargs.setdefault("current", True)
    kwargs.setdefault("date_created", datetime(2026, 6, 1))
    kwargs.setdefault("date_updated", datetime(2026, 6, 1))
    result = db.execute(credential_matches.insert().values(**kwargs))
    db.commit()
    return result.inserted_primary_key[0]

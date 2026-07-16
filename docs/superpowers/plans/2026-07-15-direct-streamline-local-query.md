# Query streamline_local Directly (Drop the Golden Profile Mirror) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop mirroring CAMI employee/credential/exclusion data into `golden_profile`; have `golden-profile-service` and `golden-profile-explorer` query `streamline_local` (the real CAMI database) live, with cross-employee canonical merging computed via a weighted score instead of a persisted boolean strong-key graph.

**Architecture:** Both Python services keep their existing FastAPI/SQLAlchemy shape. `golden-profile-service` swaps its own ORM-mirrored tables for a small SQLAlchemy Core schema (`app/streamline_schema.py`) describing the real `streamline_local` tables it reads (never writes). `resolution.py` is rewritten around a 0.0–1.0 pairwise score (exact SSN/NPI/license hits, plus name-similarity + DOB) with two thresholds splitting auto-merge / review-suggestion / unrelated, computed live per request — no persisted graph, no rebuild job. The client (`C:\new-codes\client`) drops every sync/ingest code path (observer, listeners, job, commands, supervisor worker) since there is nothing left to push into. `golden-profile-explorer` gets the same schema + scoring treatment, independently (it stays DB-direct, decoupled from the service).

**Tech Stack:** Python 3, FastAPI, SQLAlchemy 2.0 Core (no ORM mapping for tables we don't own), pytest, PyMySQL, PHP/Laravel (client removals only), PHPUnit.

## Global Constraints

- `streamline_local` is a real, shared database — every query the service/Explorer issue against it must be read-only (`SELECT` only, no `INSERT`/`UPDATE`/`DELETE`, no schema changes).
- Same MySQL server as before, different schema name: `mysql+pymysql://root:root@127.0.0.1:33066/streamline_local` locally.
- Keep these API contracts byte-for-byte unchanged (request AND response shape) so the CAMI client's search-before-scrape integration and Explorer's front-end need no changes beyond what's explicitly listed: `POST /api/v1/search/credential`, `POST /api/v1/search/general`, `GET /api/v1/resolve/employee/{id}`, `POST /api/v1/resolve/suggestions`, `GET /api/v1/stats`.
- Resolution scoring constants (module-level in `app/services/resolution.py`, not settings — they are algorithm internals, not deployment config):
  - `STRONG_SCORE = 1.0` (SSN/TIN hash exact match, NPI exact match)
  - `LICENSE_SCORE = 0.9` (shared `registry:credential_id`)
  - `NAME_WEIGHT = 0.5`, `DOB_WEIGHT = 0.4` (fuzzy combination, never on their own reaching 1.0 from name alone)
- Resolution band thresholds ARE settings (env-configurable, same pattern as `credential_ttl_days`): `resolve_merge_threshold: float = 0.85`, `resolve_suggest_threshold: float = 0.5`.
- Name is never, by itself, sufficient to auto-merge (max name-only score is `1.0 * 0.5 = 0.5`, which sits in the suggest band at the default thresholds, never the merge band) — this must hold for every threshold task below.
- No new persisted tables, no scheduled rebuild jobs, no `employee_canonical` equivalent — resolution groups are computed fresh on every call.

---

## File Structure

| File | Change |
|---|---|
| `golden-profile-service/app/streamline_schema.py` | **New.** SQLAlchemy Core `Table` objects for the real `streamline_local` tables (read-only; own `MetaData`). |
| `golden-profile-service/app/config.py` | Modify: `database_url` default → `streamline_local`; drop `resolve_use_persisted`; add `resolve_merge_threshold`, `resolve_suggest_threshold`. |
| `golden-profile-service/app/database.py` | Modify: `init_db()` now creates the Core schema (for SQLite tests only — MySQL already has the real tables). |
| `golden-profile-service/app/services/resolution.py` | Rewrite: scoring engine + union-find groups, live only. |
| `golden-profile-service/app/services/search.py` | Rewrite: query `streamline_local` via Core tables instead of the mirror ORM. |
| `golden-profile-service/app/schemas.py` | Modify: drop sync schemas; add `score`/`match_basis` fields where noted. |
| `golden-profile-service/app/routers/resolve.py` | Modify: drop `/rebuild`. |
| `golden-profile-service/app/routers/employees.py`, `credential_matches.py`, `exclusion_matches.py` | **Delete.** |
| `golden-profile-service/app/services/employee_sync.py`, `credential_sync.py`, `exclusion_sync.py` | **Delete.** |
| `golden-profile-service/app/models.py` | **Delete.** |
| `golden-profile-service/app/main.py` | Modify: drop the three deleted routers. |
| `golden-profile-service/tests/conftest.py` | Rewrite: seed helpers insert directly into the Core schema tables. |
| `golden-profile-service/tests/test_bulk_sync.py`, `test_canonical_persist.py`, `test_hotpath_persisted.py`, `test_idempotent_credential_sync.py`, `test_no_match_skip.py`, `test_observability.py` | **Delete** (test removed sync/persistence features). |
| `golden-profile-service/tests/test_resolution.py`, `test_ssn_dob_keys.py`, `test_suggestions.py`, `test_conflict.py`, `test_ttl.py`, `test_contract.py`, `test_general_resolution.py`, `test_flows.py`, `test_stats.py` | Rewrite seeding to the new schema; add scoring-band tests. |
| `client/app/Observers/GoldenProfile/CredentialMatchGoldenProfileObserver.php`, `client/app/Listeners/GoldenProfile/*`, `client/app/Jobs/GoldenProfile/PushToGoldenProfileJob.php`, `client/app/Console/Commands/GoldenProfile/GoldenProfileReconcile.php`, `GoldenProfileWork.php`, `GoldenProfileRebuildGraph.php` | **Delete.** |
| `client/provision/ansible/roles/supervisor/templates/golden_profile_worker.conf.j2` | **Delete.** |
| `client/provision/ansible/roles/supervisor/tasks/main.yml` | Modify: drop the `golden_profile_worker.conf` entry. |
| `client/app/Providers/EventServiceProvider.php` | Modify: drop the three sync-listener registrations + the two observer registrations. |
| `client/app/Providers/GoldenProfileServiceProvider.php` | Modify: drop the `GoldenProfileWork` binding. |
| `client/app/Services/GoldenProfile/GoldenProfileGateway.php` | Modify: drop all sync methods, keep `lookupCredentialData()`/`generalSearch()`. |
| `client/app/Services/GoldenProfile/GoldenProfileClient.php` | Modify: drop sync/rebuild HTTP methods, keep `searchCredential()`. |
| `client/config/services.php` | Modify: drop `sync_enabled`, `queue_enabled`, `queue_connection`, `queue`. |
| `client/app/Http/Controllers/Json/Check/EmployeeController.php` | Modify: remove the `syncEmployee()` block (lines ~411-425); keep the `lookupCredentialData()` block. |
| `client/app/Http/Controllers/Check/ListController.php` | Modify: remove `syncListEmployeesToGoldenProfile()` + its call site. |
| `golden-profile-explorer/app/db.py` | Modify: default URL → `streamline_local`. |
| `golden-profile-explorer/app/queries.py` | Rewrite: real schema + scoring-based canonical map (mirrors service `resolution.py`, duplicated on purpose — Explorer stays decoupled). |

---

### Task 1: Real-schema Core tables + config/database rewire

**Files:**
- Create: `C:\new-codes\golden-profile-service\app\streamline_schema.py`
- Modify: `C:\new-codes\golden-profile-service\app\config.py`
- Modify: `C:\new-codes\golden-profile-service\app\database.py`
- Delete: `C:\new-codes\golden-profile-service\app\models.py`
- Test: `C:\new-codes\golden-profile-service\tests\test_streamline_schema.py`

**Interfaces:**
- Produces: `app.streamline_schema.metadata` (a `sqlalchemy.MetaData`), and Core `Table` objects `employees`, `credential_matches`, `credential_match_resolutions`, `matches`, `match_actions`, `exclusion_records`, `exclusion_lists` — every later task imports these by name from `app.streamline_schema`.
- Produces: `app.database.init_db()` — unchanged signature, now builds the Core schema.
- Produces: `app.config.Settings.resolve_merge_threshold: float`, `Settings.resolve_suggest_threshold: float` (replacing `resolve_use_persisted`, which is deleted).

- [ ] **Step 1: Write the failing test for the new schema module**

```python
# tests/test_streamline_schema.py
"""The Core schema must expose every table/column the service reads."""
from app import streamline_schema as s


def test_expected_tables_are_present():
    names = set(s.metadata.tables.keys())
    assert names == {
        "employees", "credential_matches", "credential_match_resolutions",
        "matches", "match_actions", "exclusion_records", "exclusion_lists",
    }


def test_employees_columns():
    cols = set(s.employees.c.keys())
    assert {
        "id", "first_name", "last_name", "middle_name", "maiden_name", "business",
        "npi", "certification_number", "certification_state", "ssn_hash",
        "ssn_last_four", "date_of_birth", "terminated",
        "alt_first_name_1", "alt_last_name_1", "alt_first_name_2", "alt_last_name_2",
        "alt_first_name_3", "alt_last_name_3", "alt_first_name_4", "alt_last_name_4",
        "alt_first_name_5", "alt_last_name_5",
    } <= cols


def test_credential_matches_columns():
    cols = set(s.credential_matches.c.keys())
    assert {
        "id", "employee_id", "current", "registry", "type", "match",
        "date_created", "date_updated", "credential_id", "license_type_id",
        "last_modified", "expiry_date", "status", "match_summary_status",
    } <= cols


def test_matches_columns():
    cols = set(s.matches.c.keys())
    assert {
        "id", "employee_id", "exclusion_record_id", "is_npi_match",
        "is_ssn_match", "is_canonical_name_match", "is_diminutive_name_match",
        "is_aka_name_match", "is_license_number_match", "date_created",
    } <= cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\new-codes\golden-profile-service && .venv\Scripts\python.exe -m pytest tests/test_streamline_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.streamline_schema'`

- [ ] **Step 3: Write the schema module**

```python
# app/streamline_schema.py
"""Read-only view of the real streamline_local schema.

These Table objects describe columns exactly as they exist in the live CAMI
database (verified with `DESCRIBE <table>` against the local streamline_local
MySQL schema, 2026-07-15) — this service does not own this schema, does not
migrate it, and never writes to it. Only the columns the service actually
reads are declared; the real tables have more columns than listed here.

`metadata` is separate from any ORM Base — there is no declarative mapping,
no relationships, no create_all against MySQL (the real tables already
exist there). `create_all` is used only by tests against a throwaway SQLite
DB shaped like this schema.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

employees = Table(
    "employees",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("first_name", String(100)),
    Column("middle_name", String(100)),
    Column("last_name", String(100)),
    Column("maiden_name", String(100)),
    Column("alt_first_name_1", String(255)),
    Column("alt_last_name_1", String(255)),
    Column("alt_first_name_2", String(255)),
    Column("alt_last_name_2", String(255)),
    Column("alt_first_name_3", String(255)),
    Column("alt_last_name_3", String(255)),
    Column("alt_first_name_4", String(255)),
    Column("alt_last_name_4", String(255)),
    Column("alt_first_name_5", String(255)),
    Column("alt_last_name_5", String(255)),
    Column("business", String(255)),
    Column("npi", Integer),
    Column("certification_number", String(50)),
    Column("certification_state", String(65)),
    Column("ssn_hash", String(255)),
    Column("ssn_last_four", String(4)),
    Column("date_of_birth", Date),
    Column("terminated", Boolean),
)

credential_matches = Table(
    "credential_matches",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("current", Boolean),
    Column("employee_id", Integer, index=True),
    Column("match_context", Text),
    Column("registry", String(255), index=True),
    Column("type", Integer),
    Column("match", Text),
    Column("date_created", DateTime),
    Column("date_updated", DateTime),
    Column("date_resolved", DateTime),
    Column("credential_id", String(255), index=True),
    Column("license_type_id", String(100)),
    Column("last_modified", DateTime),
    Column("expiry_date", Date),
    Column("match_is_valid", Boolean),
    Column("status", String(50)),
    Column("match_summary_status", String(50)),
    Column("match_summary_status_code", Integer),
)

credential_match_resolutions = Table(
    "credential_match_resolutions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("credential_match_id", Integer, index=True),
    Column("note", Text),
    Column("created_at", DateTime),
)

matches = Table(
    "matches",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("employee_id", Integer, index=True),
    Column("exclusion_record_id", Integer, index=True),
    Column("date_contacted_agency", DateTime),
    Column("metadata", JSON),
    Column("date_created", DateTime),
    Column("date_modified", DateTime),
    Column("is_npi_match", Boolean),
    Column("is_canonical_name_match", Boolean),
    Column("is_diminutive_name_match", Boolean),
    Column("is_aka_name_match", Boolean),
    Column("is_npi_mismatch", Boolean),
    Column("is_upin_match", Boolean),
    Column("is_ssn_match", Boolean),
    Column("is_license_number_match", Boolean),
)

match_actions = Table(
    "match_actions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("action_type", String(30)),
    Column("match_id", Integer, index=True),
    Column("note", Text),
    Column("resolution_source_data", String(100)),
    Column("status", Integer),
    Column("is_dob_mismatch", Boolean),
    Column("is_ssn_mismatch", Boolean),
    Column("is_first_name_mismatch", Boolean),
    Column("is_middle_name_mismatch", Boolean),
    Column("is_last_name_mismatch", Boolean),
    Column("is_address_mismatch", Boolean),
    Column("is_npi_mismatch", Boolean),
    Column("is_job_mismatch", Boolean),
    Column("resolved_via", String(20)),
    Column("date_created", DateTime),
)

exclusion_records = Table(
    "exclusion_records",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("exclusion_list_prefix", String(25), index=True),
    Column("match", Text),
    Column("date_created", DateTime),
)

exclusion_lists = Table(
    "exclusion_lists",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("prefix", String(25), index=True),
    Column("description", Text),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_streamline_schema.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Update config.py — database URL default, drop persisted-graph flag, add score thresholds**

Edit `app/config.py`: replace the `database_url` line, remove `resolve_use_persisted`, add the two threshold settings.

```python
    database_url: str = "mysql+pymysql://root:root@127.0.0.1:33066/streamline_local"
```

Remove entirely:
```python
    # When true, general_search reads the materialized employee_canonical graph
    # ...
    resolve_use_persisted: bool = False
```

Add (near the other resolve-adjacent settings, after `no_match_statuses`):
```python
    # Resolution scoring: a candidate pair auto-merges into one canonical
    # identity at or above this score; falls into the review-only suggestions
    # band between here and resolve_suggest_threshold; below that, unrelated.
    resolve_merge_threshold: float = 0.85
    resolve_suggest_threshold: float = 0.5
```

- [ ] **Step 6: Update database.py to build the Core schema instead of the ORM mirror**

```python
# app/database.py
"""SQLAlchemy engine / session wiring."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .streamline_schema import metadata

settings = get_settings()

# SQLite needs check_same_thread=False when used from FastAPI's threadpool.
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create the schema — a no-op safety net against a real MySQL
    streamline_local (tables already exist there); builds the schema fresh
    against the throwaway SQLite DB used in tests."""
    metadata.create_all(bind=engine)
```

- [ ] **Step 7: Delete the mirror ORM module**

```bash
rm C:\new-codes\golden-profile-service\app\models.py
```

- [ ] **Step 8: Run the full schema/config/database tests to confirm nothing else broke yet**

Run: `.venv\Scripts\python.exe -m pytest tests/test_streamline_schema.py -v`
Expected: PASS (the rest of the suite is expected to fail until later tasks rewrite it — do not run the full suite yet)

- [ ] **Step 9: Commit**

```bash
git add app/streamline_schema.py app/config.py app/database.py tests/test_streamline_schema.py
git rm app/models.py
git commit -m "Replace golden_profile mirror ORM with streamline_local Core schema"
```

---

### Task 2: Resolution scoring engine (live, no persisted graph)

**Files:**
- Modify: `C:\new-codes\golden-profile-service\app\services\resolution.py` (full rewrite)
- Modify: `C:\new-codes\golden-profile-service\app\schemas.py` (drop `ResolveRebuildResult`; add `match_basis` values / `score` field)
- Delete: `C:\new-codes\golden-profile-service\app\routers\resolve.py`'s `/rebuild` route (edited in Task 4)
- Test: `C:\new-codes\golden-profile-service\tests\test_resolution.py` (rewrite), `tests\test_ssn_dob_keys.py` (rewrite), `tests\test_suggestions.py` (rewrite)
- Test: `C:\new-codes\golden-profile-service\tests\conftest.py` (add seed helpers — see Task 5, but this task needs `seed_employee`/`seed_credential_match` to exist first; write the minimal versions here and let Task 5 finish the rest)

**Interfaces:**
- Consumes: `app.streamline_schema.employees`, `app.streamline_schema.credential_matches` (Task 1).
- Produces: `resolution.score_pair(a: EmployeeKeys, b: EmployeeKeys) -> tuple[float, str]`, `resolution.group_for_seeds(db, seeds: set[int]) -> set[int]` (drops the `use_persisted` parameter — always live), `resolution.resolve_employee(db, employee_id) -> schemas.ResolveOut`, `resolution.resolve(db, payload) -> schemas.ResolveOut`, `resolution.suggestions(db, first, last) -> list[schemas.ResolveSuggestion]`. Same call signatures `search.py` (Task 3) depends on: `group_for_seeds(db, seeds)` (two args now, no `use_persisted`).

- [ ] **Step 1: Add minimal seed helpers to conftest.py (needed by this task's tests)**

```python
# tests/conftest.py — add these functions (full rewrite happens in Task 5)
from datetime import date, datetime

from app.streamline_schema import credential_matches, employees


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
```

- [ ] **Step 2: Write the failing tests for the scoring engine — replace tests/test_resolution.py**

```python
# tests/test_resolution.py
"""Entity resolution: unify records for the same real person via a weighted
score. Exact SSN/NPI/license hits alone reach the merge threshold (unchanged
behaviour from the old strong-key closure); name alone never does.
"""
from app.services import resolution


def test_shared_npi_merges_employees(db):
    from tests.conftest import seed_credential_match, seed_employee

    seed_employee(db, id=8801, first_name="Mary", last_name="Res", npi=1990000001)
    seed_employee(db, id=8802, first_name="Mary", last_name="Res", npi=1990000001)
    group = resolution.group_for_seeds(db, {8801})
    assert group == {8801, 8802}


def test_shared_license_merges_employees(db):
    from tests.conftest import seed_credential_match, seed_employee

    seed_employee(db, id=8803, first_name="Ann", last_name="ResB")
    seed_employee(db, id=8804, first_name="Anne", last_name="ResB")
    seed_credential_match(db, employee_id=8803, registry="res-b", credential_id="LIC-B")
    seed_credential_match(db, employee_id=8804, registry="res-b", credential_id="LIC-B")
    group = resolution.group_for_seeds(db, {8803})
    assert group == {8803, 8804}


def test_name_alone_never_merges(db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8805, first_name="John", last_name="MillerRes")
    seed_employee(db, id=8806, first_name="John", last_name="MillerRes")
    group = resolution.group_for_seeds(db, {8805})
    assert group == {8805}  # no DOB, no strong key -> stays separate


def test_name_plus_dob_merges_via_score(db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8842, first_name="Dana", last_name="Wyezz", date_of_birth="1990-05-05")
    seed_employee(db, id=8843, first_name="Dana", last_name="Wyezz", date_of_birth="1990-05-05")
    group = resolution.group_for_seeds(db, {8842})
    assert group == {8842, 8843}


def test_diminutive_name_plus_dob_merges(db):
    from tests.conftest import seed_employee

    # "Bob"/"Robert" is a known diminutive (name_score 0.9) + matching DOB
    # (0.4) = 0.5 + 0.4*... -> min(1.0, 0.9*0.5 + 0.4) = 0.85, at the bar.
    seed_employee(db, id=8850, first_name="Robert", last_name="Diminz", date_of_birth="1985-03-03")
    seed_employee(db, id=8851, first_name="Bob", last_name="Diminz", date_of_birth="1985-03-03")
    group = resolution.group_for_seeds(db, {8850})
    assert group == {8850, 8851}


def test_same_name_different_dob_not_merged(db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8844, first_name="Eve", last_name="Zedzz", date_of_birth="1980-01-01")
    seed_employee(db, id=8845, first_name="Eve", last_name="Zedzz", date_of_birth="1975-02-02")
    group = resolution.group_for_seeds(db, {8844})
    assert 8845 not in group


def test_shared_ssn_hash_merges(db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8840, first_name="Sam", last_name="Ecks", ssn_hash="HASH-SSN-ABC")
    seed_employee(db, id=8841, first_name="Samuel", last_name="Ecks", ssn_hash="HASH-SSN-ABC")
    group = resolution.group_for_seeds(db, {8840})
    assert group == {8840, 8841}


def test_last_four_alone_does_not_merge(db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8846, first_name="Ada", last_name="Onezz", ssn_last_four="1234")
    seed_employee(db, id=8847, first_name="Ida", last_name="Twozz", ssn_last_four="1234")
    group = resolution.group_for_seeds(db, {8846})
    assert group == {8846}


def test_resolution_is_transitive(db):
    from tests.conftest import seed_credential_match, seed_employee

    # A~B share NPI, B~C share a license -> all three resolve together.
    seed_employee(db, id=8807, first_name="Ida", last_name="ResD", npi=1990000009)
    seed_employee(db, id=8808, first_name="Ida", last_name="ResD", npi=1990000009)
    seed_employee(db, id=8809, first_name="I", last_name="ResD")
    seed_credential_match(db, employee_id=8808, registry="res-d2", credential_id="D-SHARED")
    seed_credential_match(db, employee_id=8809, registry="res-d2", credential_id="D-SHARED")
    group = resolution.group_for_seeds(db, {8807})
    assert group == {8807, 8808, 8809}


def test_resolve_employee_endpoint_reports_match_basis(client, db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8860, first_name="Merge", last_name="Basisz", npi=1990000099)
    seed_employee(db, id=8861, first_name="Merge2", last_name="Basisz", npi=1990000099)
    body = client.get("/api/v1/resolve/employee/8860").json()
    assert body["resolved"] is True
    assert sorted(body["canonical_employee_ids"]) == [8860, 8861]
    assert body["match_basis"] == "scored"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_resolution.py -v`
Expected: FAIL — old `resolution.py` API (`group_for_seeds(db, seeds, use_persisted=...)`, name-based `models.CredentialMatch`/`models.Individual`) doesn't match; several tests error before assertions.

- [ ] **Step 4: Rewrite resolution.py with the scoring engine**

```python
# app/services/resolution.py
"""Entity resolution: unify records that refer to the same real person.

Computed live, per request — no persisted graph, nothing to rebuild. Every
candidate pair of employees gets a 0.0-1.0 score:

  * SSN/TIN hash exact match         -> 1.0 (employees.ssn_hash serves both;
                                        entities store their TIN in the same
                                        column)
  * NPI exact match                  -> 1.0 (employees.npi, or the `npi` key
                                        inside a credential_matches.match blob
                                        when the employee row itself has none)
  * Shared (registry, credential_id) -> 0.9
  * Name similarity (same normalized last name required) * 0.5
    + DOB exact match * 0.4          -> fuzzy combination; on its own, name
                                        similarity tops out at 0.5 — below the
                                        merge bar, so name alone never merges.

score >= settings.resolve_merge_threshold  -> auto-merge (union-find group)
settings.resolve_suggest_threshold <= score < merge_threshold -> suggestion
score < suggest_threshold                  -> unrelated

Portable across MySQL/SQLite — identifiers are parsed in Python, no dialect
JSON functions.
"""
from __future__ import annotations

import difflib
import json
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..config import get_settings
from ..streamline_schema import credential_matches, employees

_DIMINUTIVES = {
    ("robert", "bob"), ("robert", "rob"), ("william", "bill"), ("william", "will"),
    ("richard", "rick"), ("richard", "dick"), ("michael", "mike"), ("james", "jim"),
    ("katherine", "kathy"), ("katherine", "kate"), ("elizabeth", "liz"),
    ("elizabeth", "beth"), ("margaret", "peggy"), ("charles", "chuck"),
    ("thomas", "tom"), ("joseph", "joe"), ("john", "jack"), ("daniel", "dan"),
}

STRONG_SCORE = 1.0
LICENSE_SCORE = 0.9
NAME_WEIGHT = 0.5
DOB_WEIGHT = 0.4


def _norm(value) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _first_name_score(a: str, b: str) -> tuple[float, str]:
    """Similarity of two given names -> (score 0..1, reason). 0 = not similar."""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0, ""
    if a == b:
        return 0.95, "same name"
    lo, hi = sorted((a, b), key=len)
    if len(lo) == 1 and hi.startswith(lo):
        return 0.6, "initial matches"
    if len(lo) >= 2 and hi.startswith(lo):
        return 0.85, "one name is a prefix of the other"
    if (a, b) in _DIMINUTIVES or (b, a) in _DIMINUTIVES:
        return 0.9, "known nickname"
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    if ratio >= 0.8:
        return round(ratio, 2), "spelling is close"
    return 0.0, ""


def _npi_from_match(raw: str | None) -> str | None:
    try:
        data = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return None
    if isinstance(data, dict):
        npi = _digits(data.get("npi"))
        return npi or None
    return None


@dataclass
class EmployeeKeys:
    employee_id: int
    first_name: str = ""
    last_name: str = ""
    date_of_birth: object = None  # date | None
    ssn_hash: str | None = None
    npi: str | None = None
    licenses: set[str] = field(default_factory=set)


def _load_employee_keys(db: Session, employee_ids: set[int]) -> dict[int, EmployeeKeys]:
    """Load scoring inputs for a bounded set of employees (never the whole DB —
    callers scope this to name/last-name candidates first)."""
    if not employee_ids:
        return {}
    out: dict[int, EmployeeKeys] = {}
    rows = db.execute(
        select(
            employees.c.id, employees.c.first_name, employees.c.last_name,
            employees.c.date_of_birth, employees.c.ssn_hash, employees.c.npi,
        ).where(employees.c.id.in_(employee_ids))
    )
    for eid, first, last, dob, ssn_hash, npi in rows:
        out[eid] = EmployeeKeys(
            employee_id=eid, first_name=first or "", last_name=last or "",
            date_of_birth=dob, ssn_hash=ssn_hash or None,
            npi=_digits(npi) or None,
        )
    cm_rows = db.execute(
        select(
            credential_matches.c.employee_id, credential_matches.c.registry,
            credential_matches.c.credential_id, credential_matches.c.match,
        ).where(credential_matches.c.employee_id.in_(employee_ids))
    )
    for eid, registry, cred_id, match in cm_rows:
        keys = out.setdefault(eid, EmployeeKeys(employee_id=eid))
        if registry and cred_id:
            keys.licenses.add(f"{str(registry).strip().lower()}:{str(cred_id).strip()}")
        if not keys.npi:
            npi = _npi_from_match(match)
            if npi:
                keys.npi = npi
    return out


def score_pair(a: EmployeeKeys, b: EmployeeKeys) -> tuple[float, str]:
    """0.0-1.0 similarity score for a candidate pair, and a human reason."""
    if a.ssn_hash and a.ssn_hash == b.ssn_hash:
        return STRONG_SCORE, "shared SSN/TIN hash"
    if a.npi and a.npi == b.npi:
        return STRONG_SCORE, "shared NPI"
    shared_license = a.licenses & b.licenses
    if shared_license:
        return LICENSE_SCORE, f"shared license {sorted(shared_license)[0]}"

    if _norm(a.last_name) != _norm(b.last_name):
        return 0.0, ""
    name_score, name_reason = _first_name_score(a.first_name, b.first_name)
    if name_score <= 0:
        return 0.0, ""
    dob_match = bool(a.date_of_birth and b.date_of_birth and a.date_of_birth == b.date_of_birth)
    score = min(1.0, name_score * NAME_WEIGHT + (DOB_WEIGHT if dob_match else 0.0))
    if score <= 0:
        return 0.0, ""
    reason = f"{name_reason} + matching DOB" if dob_match else name_reason
    return round(score, 2), reason


class _UnionFind:
    def __init__(self, items: set[int]):
        self.parent = {i: i for i in items}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def groups(self) -> dict[int, set[int]]:
        out: dict[int, set[int]] = defaultdict(set)
        for i in self.parent:
            out[self.find(i)].add(i)
        return dict(out)


def _candidate_scope(db: Session, seeds: set[int]) -> set[int]:
    """Every employee sharing a last name (normalized) OR a strong key with any
    seed — bounds the pairwise comparison instead of scanning the whole table."""
    seed_keys = _load_employee_keys(db, seeds)
    last_names = {_norm(k.last_name) for k in seed_keys.values() if k.last_name}
    scope = set(seeds)
    if last_names:
        rows = db.execute(select(employees.c.id, employees.c.last_name))
        scope |= {eid for eid, last in rows if _norm(last) in last_names}
    return scope


def _grouped_scores(db: Session, seeds: set[int], threshold: float) -> set[int]:
    """Union every employee in the candidate scope reachable from `seeds` via
    an edge scoring >= threshold; returns the seeds' resulting group."""
    if not seeds:
        return set()
    scope = _candidate_scope(db, seeds)
    keys = _load_employee_keys(db, scope)
    uf = _UnionFind(set(keys))
    ids = sorted(keys)
    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1:]:
            score, _ = score_pair(keys[a_id], keys[b_id])
            if score >= threshold:
                uf.union(a_id, b_id)
    groups = uf.groups()
    result: set[int] = set()
    for seed in seeds:
        if seed in uf.parent:
            result |= groups[uf.find(seed)]
        else:
            result.add(seed)
    return result


def group_for_seeds(db: Session, seeds: set[int]) -> set[int]:
    """Canonical group for a set of seed employees, computed live."""
    return _grouped_scores(db, seeds, get_settings().resolve_merge_threshold)


def suggestions(db: Session, first: str, last: str) -> list[schemas.ResolveSuggestion]:
    """Review-only candidates: score in [suggest_threshold, merge_threshold) —
    never auto-merged. Powered by the same scorer as auto-merge."""
    first, last = (first or "").strip(), (last or "").strip()
    if not first or not last:
        return []
    settings = get_settings()

    rows = db.execute(
        select(employees.c.id).where(employees.c.first_name == first).where(employees.c.last_name == last)
    )
    seeds = {r[0] for r in rows}
    if not seeds:
        # Still allow suggestions for a query name with no exact-match employee.
        scope = db.execute(select(employees.c.id, employees.c.last_name))
        seeds = {eid for eid, ln in scope if _norm(ln) == _norm(last)} or set()

    merged = _grouped_scores(db, seeds, settings.resolve_merge_threshold) if seeds else set()

    scope_ids = _candidate_scope(db, seeds or {-1})
    keys = _load_employee_keys(db, scope_ids | seeds)
    query_key = EmployeeKeys(employee_id=-1, first_name=first, last_name=last)

    best: dict[int, schemas.ResolveSuggestion] = {}
    for eid, k in keys.items():
        if eid in merged or eid in seeds:
            continue
        if _norm(k.last_name) != _norm(last):
            continue
        score, reason = score_pair(query_key, k)
        if score < settings.resolve_suggest_threshold or score >= settings.resolve_merge_threshold:
            continue
        existing = best.get(eid)
        if existing is None or score > existing.score:
            best[eid] = schemas.ResolveSuggestion(
                cami_employee_id=eid, first_name=k.first_name, last_name=k.last_name,
                score=score, reason=reason,
            )
    return sorted(best.values(), key=lambda s: s.score, reverse=True)


def _identifiers(db: Session, group: set[int]) -> schemas.ResolveIdentifiers:
    if not group:
        return schemas.ResolveIdentifiers()
    keys = _load_employee_keys(db, group)
    npis: set[str] = set()
    licenses: dict[tuple[str, str], schemas.ResolveLicense] = {}
    for k in keys.values():
        if k.npi:
            npis.add(k.npi)
        for lic in k.licenses:
            reg, num = lic.split(":", 1)
            licenses[(reg, num)] = schemas.ResolveLicense(registry=reg, number=num)
    return schemas.ResolveIdentifiers(npi=sorted(npis), licenses=list(licenses.values()))


def _names(db: Session, group: set[int]) -> list[schemas.ResolveName]:
    if not group:
        return []
    rows = db.execute(
        select(employees.c.first_name, employees.c.last_name).where(employees.c.id.in_(group)).distinct()
    )
    return [schemas.ResolveName(first=first, last=last) for first, last in rows]


def resolve_employee(db: Session, employee_id: int) -> schemas.ResolveOut:
    """Live per-employee lookup — computed on every call, no persisted table."""
    exists = db.execute(select(employees.c.id).where(employees.c.id == employee_id)).first()
    if exists is None:
        return schemas.ResolveOut(
            resolved=False, match_basis="none", canonical_employee_ids=[],
            name_only_candidates=[], identifiers=schemas.ResolveIdentifiers(), names=[],
        )
    group = group_for_seeds(db, {employee_id})
    return schemas.ResolveOut(
        resolved=len(group) > 1,
        match_basis="scored",
        canonical_employee_ids=sorted(group),
        name_only_candidates=[],
        identifiers=_identifiers(db, group),
        names=_names(db, group),
    )


def _license_key(registry: str | None, number: str | None) -> str | None:
    reg = (registry or "").strip().lower()
    num = (number or "").strip()
    return f"{reg}:{num}" if reg and num else None


def _name_candidates(db: Session, first: str, last: str) -> list[int]:
    rows = db.execute(
        select(employees.c.id).where(employees.c.first_name == first).where(employees.c.last_name == last).distinct()
    )
    return sorted({r[0] for r in rows})


def resolve(db: Session, payload: schemas.ResolveIn) -> schemas.ResolveOut:
    if payload.npi and _digits(payload.npi):
        npi = _digits(payload.npi)
        rows = db.execute(select(employees.c.id).where(employees.c.npi == int(npi)))
        seeds = {r[0] for r in rows}
        if not seeds:
            cm_rows = db.execute(select(credential_matches.c.employee_id, credential_matches.c.match))
            seeds = {eid for eid, match in cm_rows if _npi_from_match(match) == npi}
        group = group_for_seeds(db, seeds) if seeds else set()
        return schemas.ResolveOut(
            resolved=bool(group), match_basis="npi", canonical_employee_ids=sorted(group),
            name_only_candidates=[], identifiers=_identifiers(db, group), names=_names(db, group),
        )

    if payload.license_number and payload.registry:
        key = _license_key(payload.registry, payload.license_number)
        rows = db.execute(
            select(credential_matches.c.employee_id)
            .where(credential_matches.c.registry == payload.registry)
            .where(credential_matches.c.credential_id == payload.license_number)
        )
        seeds = {r[0] for r in rows}
        group = group_for_seeds(db, seeds) if seeds else set()
        return schemas.ResolveOut(
            resolved=bool(group), match_basis="license", canonical_employee_ids=sorted(group),
            name_only_candidates=[], identifiers=_identifiers(db, group), names=_names(db, group),
        )

    if payload.params_first_name and payload.params_last_name:
        candidates = _name_candidates(db, payload.params_first_name, payload.params_last_name)
        return schemas.ResolveOut(
            resolved=False, match_basis="name_only", canonical_employee_ids=[],
            name_only_candidates=candidates, identifiers=schemas.ResolveIdentifiers(), names=[],
        )

    return schemas.ResolveOut(
        resolved=False, match_basis="none", canonical_employee_ids=[],
        name_only_candidates=[], identifiers=schemas.ResolveIdentifiers(), names=[],
    )
```

- [ ] **Step 5: Update schemas.py — drop the rebuild result, document match_basis values**

In `app/schemas.py`, delete the `ResolveRebuildResult` class entirely, and update the `ResolveOut.match_basis` docstring/comment:

```python
class ResolveOut(BaseModel):
    # True only when a strong identifier or a high enough fuzzy score produced
    # a canonical group.
    resolved: bool
    # How the group was anchored: "npi" | "license" | "scored" | "name_only" | "none".
    match_basis: str
```

(Everything else in `ResolveOut` is unchanged.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_resolution.py -v`
Expected: PASS (10 tests) — note `resolve_employee_endpoint` test will still fail until Task 4 removes the `/rebuild` route reference and Task 3 stops importing dead `search.py` symbols; if it fails on an import error from `search.py`, proceed to Task 3 before re-running.

- [ ] **Step 7: Rewrite test_ssn_dob_keys.py and test_suggestions.py against the new API**

```python
# tests/test_ssn_dob_keys.py
"""SSN (hash) and name+DOB as resolution signals, expressed as scores."""
from tests.conftest import seed_employee


def test_shared_ssn_hash_merges(db):
    from app.services import resolution

    seed_employee(db, id=9840, first_name="Sam", last_name="Eckz", ssn_hash="HASH-1")
    seed_employee(db, id=9841, first_name="Samuel", last_name="Eckz", ssn_hash="HASH-1")
    assert resolution.group_for_seeds(db, {9840}) == {9840, 9841}


def test_name_plus_dob_merges(db):
    from app.services import resolution

    seed_employee(db, id=9842, first_name="Dana", last_name="Wyez", date_of_birth="1990-05-05")
    seed_employee(db, id=9843, first_name="Dana", last_name="Wyez", date_of_birth="1990-05-05")
    assert resolution.group_for_seeds(db, {9842}) == {9842, 9843}


def test_same_name_different_dob_not_merged(db):
    from app.services import resolution

    seed_employee(db, id=9844, first_name="Eve", last_name="Zedz", date_of_birth="1980-01-01")
    seed_employee(db, id=9845, first_name="Eve", last_name="Zedz", date_of_birth="1975-02-02")
    assert 9845 not in resolution.group_for_seeds(db, {9844})


def test_last_four_alone_does_not_merge(db):
    from app.services import resolution

    seed_employee(db, id=9846, first_name="Ada", last_name="Onez", ssn_last_four="1234")
    seed_employee(db, id=9847, first_name="Ida", last_name="Twoz", ssn_last_four="1234")
    assert resolution.group_for_seeds(db, {9846}) == {9846}
```

```python
# tests/test_suggestions.py
"""Fuzzy name-variant SUGGESTIONS — review-only band, never an auto-merge."""
from tests.conftest import seed_employee


def _suggest(client, first, last):
    return client.post("/api/v1/resolve/suggestions",
                       json={"params_first_name": first, "params_last_name": last}).json()


def test_prefix_variant_is_suggested(client, db):
    seed_employee(db, id=8830, first_name="Robert", last_name="Jonez")
    seed_employee(db, id=8831, first_name="Rob", last_name="Jonez")
    ids = [s["cami_employee_id"] for s in _suggest(client, "Robert", "Jonez")["suggestions"]]
    assert 8831 in ids
    assert 8830 not in ids  # the query's own record is never suggested back


def test_already_strong_linked_not_suggested(client, db):
    seed_employee(db, id=8832, first_name="Kathy", last_name="Smithx", npi=1930000001)
    seed_employee(db, id=8833, first_name="Katherine", last_name="Smithx", npi=1930000001)
    ids = [s["cami_employee_id"] for s in _suggest(client, "Kathy", "Smithx")["suggestions"]]
    assert 8833 not in ids  # already merged, not a suggestion


def test_different_last_name_not_suggested(client, db):
    seed_employee(db, id=8834, first_name="Zed", last_name="Alphaz")
    seed_employee(db, id=8835, first_name="Zed", last_name="Betaz")
    ids = [s["cami_employee_id"] for s in _suggest(client, "Zed", "Alphaz")["suggestions"]]
    assert 8835 not in ids


def test_suggestion_carries_score_and_reason(client, db):
    seed_employee(db, id=8836, first_name="Maria", last_name="Santosz")
    seed_employee(db, id=8837, first_name="M", last_name="Santosz")
    sug = _suggest(client, "Maria", "Santosz")["suggestions"]
    hit = [s for s in sug if s["cami_employee_id"] == 8837]
    assert hit and 0 < hit[0]["score"] < 0.85 and hit[0]["reason"]
```

- [ ] **Step 8: Run all resolution-related tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_resolution.py tests/test_ssn_dob_keys.py tests/test_suggestions.py -v`
Expected: PASS (may still fail on app startup if `search.py`/routers reference deleted symbols — if so, note the failure and proceed to Task 3/4, then return here)

- [ ] **Step 9: Commit**

```bash
git add app/services/resolution.py app/schemas.py tests/test_resolution.py tests/test_ssn_dob_keys.py tests/test_suggestions.py tests/conftest.py
git commit -m "Rewrite resolution as a live weighted score (drop persisted graph)"
```

---

### Task 3: Search service rewrite (search_credential + general_search)

**Files:**
- Modify: `C:\new-codes\golden-profile-service\app\services\search.py` (full rewrite)
- Test: `C:\new-codes\golden-profile-service\tests\test_ttl.py`, `tests\test_conflict.py`, `tests\test_contract.py`, `tests\test_general_resolution.py`, `tests\test_flows.py` (rewrite seeding)

**Interfaces:**
- Consumes: `app.streamline_schema.employees`, `credential_matches`, `credential_match_resolutions` (Task 1); `resolution.group_for_seeds(db, seeds)` (Task 2, two-arg form).
- Produces: `search.search_credential(db, payload) -> schemas.CredentialSearchResult`, `search.general_search(db, payload) -> schemas.GeneralSearchResult` — same signatures as before; routers (Task 4) call these unchanged.

- [ ] **Step 1: Write the failing TTL test (staleness now keyed on date_updated, no check_date column)**

```python
# tests/test_ttl.py
"""Cache-freshness (TTL) behaviour of the credential search."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.services import search as search_service
from tests.conftest import seed_credential_match, seed_employee


def _days_ago(days: int) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


def _seed(db, *, updated_days_ago: int, registry="nursysttl", emp=501):
    seed_employee(db, id=emp, first_name="Jane", last_name="Doe")
    seed_credential_match(
        db, employee_id=emp, registry=registry, credential_id="L-TTL-1",
        status="VALID", match_summary_status="Valid",
        match='{"response_code": "0", "npi": "1234567890"}',
        date_updated=_days_ago(updated_days_ago),
        date_created=_days_ago(updated_days_ago),
    )


def _search(client, registry="nursysttl", first="Jane", last="Doe"):
    return client.post(
        "/api/v1/search/credential",
        json={
            "registry_prefix": registry, "params_first_name": first,
            "params_last_name": last, "params_credential_id": "L-TTL-1",
        },
    )


def test_ttl_disabled_serves_any_age(client, db, monkeypatch):
    monkeypatch.setattr(search_service, "get_settings", lambda: Settings(credential_ttl_days=0))
    _seed(db, updated_days_ago=400)
    body = _search(client).json()
    assert body["found"] is True
    assert body["action"] == "return_result"
    assert body["age_days"] >= 399


def test_ttl_stale_match_triggers_scrape(client, db, monkeypatch):
    monkeypatch.setattr(search_service, "get_settings", lambda: Settings(credential_ttl_days=30))
    _seed(db, updated_days_ago=400, registry="nursysttl2", emp=502)
    body = _search(client, registry="nursysttl2", first="Jane", last="Doe").json()
    assert body["found"] is False
    assert body["action"] == "trigger_scrape"
    assert "stale" in body["reason"].lower()


def test_ttl_fresh_match_still_served(client, db, monkeypatch):
    monkeypatch.setattr(search_service, "get_settings", lambda: Settings(credential_ttl_days=30))
    _seed(db, updated_days_ago=5, registry="nursysttl3", emp=503)
    body = _search(client, registry="nursysttl3", first="Jane", last="Doe").json()
    assert body["found"] is True
    assert body["action"] == "return_result"


def test_ttl_per_registry_override(client, db, monkeypatch):
    monkeypatch.setattr(
        search_service, "get_settings",
        lambda: Settings(credential_ttl_days=365, credential_ttl_overrides='{"nursysttl4": 1}'),
    )
    _seed(db, updated_days_ago=10, registry="nursysttl4", emp=504)
    body = _search(client, registry="nursysttl4", first="Jane", last="Doe").json()
    assert body["found"] is False
    assert body["action"] == "trigger_scrape"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ttl.py -v`
Expected: FAIL (old `search.py` still imports `models`)

- [ ] **Step 3: Rewrite search.py against the real schema**

```python
# app/services/search.py
"""Process: Credentialing Search Changes.

When CAMI performs a check for a registry, it asks the Golden Profile first
(now: queries streamline_local directly, live — no sync lag).

  1. Look for a VALID, current credential_match matching the params (freshest
     first, joined to employees for the name).
        -> found  => return_result
  2. Otherwise look for a credential_match matching the params (ignoring name)
     that carries a name-mismatch resolution (credential_match_resolutions).
        -> found  => auto_resolve_name_mismatch
        -> none   => trigger_scrape
  3. Nothing matches at all => trigger_scrape
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import metrics, schemas
from ..config import get_settings
from ..streamline_schema import credential_match_resolutions, credential_matches, employees
from . import resolution

log = logging.getLogger("golden_profile.search")


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _row_age_days(date_updated, date_created) -> int | None:
    stamp = date_updated or date_created
    if stamp is None:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return max((now - stamp).days, 0)


def _is_stale(date_updated, date_created, ttl_days: int) -> bool:
    if ttl_days <= 0:
        return False
    age = _row_age_days(date_updated, date_created)
    return age is not None and age > ttl_days


def _npi_ok(match_json: str | None, npi: str | None) -> bool:
    want = _digits(npi)
    if not want:
        return True
    try:
        data = json.loads(match_json) if match_json else {}
    except (ValueError, TypeError):
        return False
    return isinstance(data, dict) and _digits(str(data.get("npi") or "")) == want


def _is_valid(status: str | None, match_summary_status: str | None, expiry_date) -> bool:
    valid_statuses = get_settings().valid_status_set
    status_ok = (match_summary_status or "").upper() in valid_statuses or (status or "").upper() in valid_statuses
    if not status_ok:
        return False
    if expiry_date is not None and expiry_date < date.today():
        return False
    return True


def _cm_out(row) -> schemas.CredentialMatchOut:
    return schemas.CredentialMatchOut(
        id=row.id,
        cami_employee_id=row.employee_id,
        cami_credential_match_id=row.id,
        registry=row.registry,
        params_first_name=row.first_name,
        params_middle_name=None,
        params_last_name=row.last_name,
        params_credential_id=row.credential_id,
        params_license_type=row.license_type_id,
        match_summary_status=row.match_summary_status,
        match_context=None,
        match=row.match,
        status=row.status,
        expiry_date=row.expiry_date,
        check_date=row.date_updated or row.date_created,
    )


def search_credential(db: Session, payload: schemas.CredentialSearchIn) -> schemas.CredentialSearchResult:
    registry = (payload.registry or "").strip().lower()
    ttl_days = get_settings().ttl_for_prefix(registry)

    base = (
        select(
            credential_matches.c.id, credential_matches.c.employee_id,
            credential_matches.c.registry, credential_matches.c.credential_id,
            credential_matches.c.license_type_id, credential_matches.c.match_summary_status,
            credential_matches.c.match, credential_matches.c.status,
            credential_matches.c.expiry_date, credential_matches.c.date_created,
            credential_matches.c.date_updated,
            employees.c.first_name, employees.c.last_name,
        )
        .select_from(credential_matches.join(employees, credential_matches.c.employee_id == employees.c.id))
        .where(func.lower(credential_matches.c.registry) == registry)
        .where(credential_matches.c.current.is_(True))
    )
    if payload.params_credential_id:
        base = base.where(credential_matches.c.credential_id == payload.params_credential_id)
    if payload.params_license_type:
        base = base.where(credential_matches.c.license_type_id == payload.params_license_type)

    named = base
    if payload.params_last_name:
        named = named.where(func.lower(employees.c.last_name) == payload.params_last_name.lower())
    if payload.params_first_name:
        named = named.where(func.lower(employees.c.first_name) == payload.params_first_name.lower())
    named = named.order_by(
        credential_matches.c.date_updated.is_(None),
        credential_matches.c.date_updated.desc(),
        credential_matches.c.id.desc(),
    )

    for row in db.execute(named):
        if _is_valid(row.status, row.match_summary_status, row.expiry_date) and _npi_ok(row.match, payload.npi):
            age = _row_age_days(row.date_updated, row.date_created)
            if _is_stale(row.date_updated, row.date_created, ttl_days):
                metrics.incr(metrics.SEARCH_STALE)
                metrics.incr(metrics.SEARCH_MISS)
                log.info(
                    "search.credential registry=%s action=trigger_scrape reason=stale age_days=%s ttl_days=%s",
                    registry, age, ttl_days,
                )
                return schemas.CredentialSearchResult(
                    found=False, action="trigger_scrape",
                    reason=f"Cached match is stale (age {age}d > TTL {ttl_days}d); trigger bot scrape.",
                    age_days=age,
                )
            metrics.incr(metrics.SEARCH_HIT)
            metrics.record_hit_age(age)
            log.info("search.credential registry=%s action=return_result age_days=%s", registry, age)
            return schemas.CredentialSearchResult(
                found=True, action="return_result",
                reason="Valid credential match found in Golden Profile.",
                credential_match=_cm_out(row), age_days=age,
            )

    unnamed = base.order_by(credential_matches.c.id.desc())
    for row in db.execute(unnamed):
        if not _npi_ok(row.match, payload.npi):
            continue
        if _is_stale(row.date_updated, row.date_created, ttl_days):
            continue
        resolution_row = db.execute(
            select(credential_match_resolutions.c.id, credential_match_resolutions.c.note,
                   credential_match_resolutions.c.created_at)
            .where(credential_match_resolutions.c.credential_match_id == row.id)
            .order_by(credential_match_resolutions.c.id.desc())
        ).first()
        if resolution_row is not None:
            age = _row_age_days(row.date_updated, row.date_created)
            metrics.incr(metrics.SEARCH_HIT)
            metrics.incr(metrics.SEARCH_RESOLVE)
            metrics.record_hit_age(age)
            log.info("search.credential registry=%s action=auto_resolve_name_mismatch age_days=%s", registry, age)
            return schemas.CredentialSearchResult(
                found=True, action="auto_resolve_name_mismatch",
                reason="Credential match found with a recorded name-mismatch resolution; auto-resolving.",
                credential_match=_cm_out(row),
                resolution=schemas.ResolutionOut(
                    id=resolution_row.id, credential_match_id=row.id,
                    note=resolution_row.note, date_created=resolution_row.created_at,
                ),
                age_days=age,
            )

    metrics.incr(metrics.SEARCH_MISS)
    log.info("search.credential registry=%s action=trigger_scrape reason=no_match", registry)
    return schemas.CredentialSearchResult(
        found=False, action="trigger_scrape",
        reason="No valid match or resolution in Golden Profile; trigger bot scrape.",
    )


def _name_seed_employees(db: Session, first: str, last: str) -> set[int]:
    rows = db.execute(
        select(employees.c.id)
        .where(func.lower(employees.c.first_name) == first)
        .where(func.lower(employees.c.last_name) == last)
    )
    return {r[0] for r in rows}


def general_search(db: Session, payload: schemas.GeneralSearchIn) -> schemas.GeneralSearchResult:
    first = payload.params_first_name.strip().lower()
    last = payload.params_last_name.strip().lower()

    seeds = _name_seed_employees(db, first, last)
    group = resolution.group_for_seeds(db, seeds) if (payload.resolve and seeds) else seeds

    cm_stmt = (
        select(
            credential_matches.c.id, credential_matches.c.employee_id,
            credential_matches.c.registry, credential_matches.c.credential_id,
            credential_matches.c.license_type_id, credential_matches.c.match_summary_status,
            credential_matches.c.match, credential_matches.c.status,
            credential_matches.c.expiry_date, credential_matches.c.date_created,
            credential_matches.c.date_updated,
            employees.c.first_name, employees.c.last_name,
        )
        .select_from(credential_matches.join(employees, credential_matches.c.employee_id == employees.c.id))
        .where(credential_matches.c.current.is_(True))
    )
    cm_stmt = cm_stmt.where(credential_matches.c.employee_id.in_(group)) if group else cm_stmt.where(
        credential_matches.c.employee_id == -1
    )
    if payload.params_credential_id:
        cm_stmt = cm_stmt.where(credential_matches.c.credential_id == payload.params_credential_id)
    if not payload.include_expired:
        cm_stmt = cm_stmt.where(
            or_(credential_matches.c.expiry_date.is_(None), credential_matches.c.expiry_date >= date.today())
        )
    if payload.exclude_no_matches:
        cm_stmt = cm_stmt.where(credential_matches.c.status != "2")
    cm_stmt = cm_stmt.order_by(
        credential_matches.c.date_updated.is_(None),
        credential_matches.c.date_updated.desc(),
        credential_matches.c.id.desc(),
    )

    latest_by_registry: dict[str | None, object] = {}
    by_registry_license: dict[tuple, list] = {}
    for row in db.execute(cm_stmt):
        if not _npi_ok(row.match, payload.npi):
            continue
        latest_by_registry.setdefault(row.registry, row)
        by_registry_license.setdefault((row.registry, row.credential_id), []).append(row)

    credential_matches_out = []
    for row in latest_by_registry.values():
        winner_valid = _is_valid(row.status, row.match_summary_status, row.expiry_date)
        conflicts = []
        for other in by_registry_license.get((row.registry, row.credential_id), []):
            if other.id == row.id:
                continue
            other_valid = _is_valid(other.status, other.match_summary_status, other.expiry_date)
            if other_valid != winner_valid:
                conflicts.append(schemas.GeneralCredentialConflictOut(
                    id=other.id, valid=other_valid, match_summary_status=other.match_summary_status,
                    status=other.status, expiry_date=other.expiry_date,
                    check_date=other.date_updated or other.date_created,
                ))
        if conflicts:
            metrics.incr(metrics.SEARCH_CONFLICT)
            log.info(
                "search.general registry=%s credential_id=%s has_conflict=true winner_id=%s conflict_ids=%s",
                row.registry, row.credential_id, row.id, ",".join(str(c.id) for c in conflicts),
            )
        credential_matches_out.append(schemas.GeneralCredentialMatchOut(
            id=row.id, cami_employee_id=row.employee_id, registry=row.registry,
            params_first_name=row.first_name, params_middle_name=None, params_last_name=row.last_name,
            params_credential_id=row.credential_id, params_license_type=row.license_type_id,
            match_summary_status=row.match_summary_status, status=row.status,
            expiry_date=row.expiry_date, check_date=row.date_updated or row.date_created,
            match=row.match, has_conflict=bool(conflicts), conflicts=conflicts,
        ))

    exclusion_matches_out = _general_exclusion_matches(db, group)

    return schemas.GeneralSearchResult(
        params_first_name=payload.params_first_name, params_last_name=payload.params_last_name,
        params_credential_id=payload.params_credential_id, include_expired=payload.include_expired,
        exclude_no_matches=payload.exclude_no_matches, canonical_employee_ids=sorted(group),
        credential_matches=credential_matches_out, exclusion_matches=exclusion_matches_out,
    )


def _general_exclusion_matches(db: Session, group: set[int]) -> list[schemas.GeneralExclusionMatchOut]:
    from ..streamline_schema import exclusion_lists, exclusion_records, matches as matches_table

    if not group:
        return []
    stmt = (
        select(
            matches_table.c.id, matches_table.c.employee_id, matches_table.c.exclusion_record_id,
            matches_table.c.is_npi_match, matches_table.c.is_ssn_match,
            matches_table.c.is_license_number_match, matches_table.c.date_created,
            exclusion_records.c.exclusion_list_prefix, exclusion_records.c.match,
            employees.c.first_name, employees.c.last_name,
        )
        .select_from(
            matches_table
            .join(exclusion_records, matches_table.c.exclusion_record_id == exclusion_records.c.id)
            .join(employees, matches_table.c.employee_id == employees.c.id)
        )
        .where(matches_table.c.employee_id.in_(group))
        .order_by(matches_table.c.id.desc())
    )
    out = []
    seen: set[tuple[int, str | None]] = set()
    for row in db.execute(stmt):
        key = (row.employee_id, row.exclusion_list_prefix)
        if key in seen:
            continue
        seen.add(key)
        out.append(schemas.GeneralExclusionMatchOut(
            id=row.id, cami_employee_id=row.employee_id, cami_match_id=row.id,
            prefix=row.exclusion_list_prefix, params_first_name=row.first_name,
            params_middle_name=None, params_last_name=row.last_name, match=row.match,
            is_npi_match=bool(row.is_npi_match), is_ssn_match=bool(row.is_ssn_match),
            is_license_number_match=bool(row.is_license_number_match),
            check_date=row.date_created,
        ))
    return out
```

**Note (known behavior deviation, acceptable per spec's non-goals):** the mirror stored `params_first_name`/`params_last_name` on the credential-match row itself (the name *as checked at that time*). The real `credential_matches` table has no such column — this rewrite joins the *current* `employees.first_name`/`last_name` instead. If an employee is renamed after a check, `general_search`'s reported name reflects the rename, not the historical name-at-check-time. This is a minor, acceptable fidelity loss (flagged here, not silently absorbed).

- [ ] **Step 4: Run TTL tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ttl.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Rewrite test_conflict.py, test_contract.py, test_general_resolution.py, test_flows.py seeding**

Apply the same seeding pattern (`seed_employee` + `seed_credential_match` from `tests/conftest.py`, `date_updated`/`current=True` instead of `check_date`, `credential_id` instead of `params_credential_id`, `registry` unchanged) to each of these four files — mechanical find/replace of the seeding helper, assertions unchanged since the response schema (`schemas.py`) contract didn't change. Example for `test_conflict.py`:

```python
# tests/test_conflict.py
"""Conflict flagging in the general (name-based) search."""
from tests.conftest import seed_credential_match, seed_employee


def _post_match(db, *, emp, first, last, registry, cred, status, summary, updated):
    seed_employee(db, id=emp, first_name=first, last_name=last)
    return seed_credential_match(
        db, employee_id=emp, registry=registry, credential_id=cred,
        status=status, match_summary_status=summary,
        match='{"response_code":2}', date_updated=updated, date_created=updated,
    )


def test_general_search_flags_conflicting_status(client, db):
    from datetime import datetime

    first, last, emp, reg = "Cora", "ConflictA", 9600, "conf-a-ny"
    old_id = _post_match(db, emp=emp, first=first, last=last, registry=reg, cred="NY-900",
                         status="1", summary="Invalid - Expired", updated=datetime(2025, 1, 1))
    new_id = _post_match(db, emp=emp + 1000, first=first, last=last, registry=reg, cred="NY-900",
                         status="VALID", summary="Valid", updated=datetime(2026, 6, 1))

    body = client.post("/api/v1/search/general",
                       json={"params_first_name": first, "params_last_name": last}).json()
    matches = [m for m in body["credential_matches"] if m["registry"] == reg]
    assert len(matches) == 1
    winner = matches[0]
    assert winner["id"] == new_id
    assert winner["has_conflict"] is True
    assert len(winner["conflicts"]) == 1
    assert winner["conflicts"][0]["id"] == old_id
    assert winner["conflicts"][0]["valid"] is False


def test_general_search_no_conflict_when_snapshots_agree(client, db):
    from datetime import datetime

    first, last, emp, reg = "Cora", "ConflictB", 9601, "conf-b-ny"
    _post_match(db, emp=emp, first=first, last=last, registry=reg, cred="NY-901",
                status="VALID", summary="Valid", updated=datetime(2025, 1, 1))
    _post_match(db, emp=emp + 1000, first=first, last=last, registry=reg, cred="NY-901",
                status="VALID", summary="Valid", updated=datetime(2026, 6, 1))

    body = client.post("/api/v1/search/general",
                       json={"params_first_name": first, "params_last_name": last}).json()
    matches = [m for m in body["credential_matches"] if m["registry"] == reg]
    assert len(matches) == 1
    assert matches[0]["has_conflict"] is False
    assert matches[0]["conflicts"] == []


def test_general_search_different_registries_are_not_a_conflict(client, db):
    from datetime import datetime

    first, last, emp = "Cora", "ConflictC", 9602
    _post_match(db, emp=emp, first=first, last=last, registry="conf-c-ny", cred="NY-902",
                status="VALID", summary="Valid", updated=datetime(2026, 6, 1))
    _post_match(db, emp=emp + 1000, first=first, last=last, registry="conf-c-ca", cred="CA-902",
                status="1", summary="Invalid - Expired", updated=datetime(2026, 6, 1))

    body = client.post("/api/v1/search/general",
                       json={"params_first_name": first, "params_last_name": last}).json()
    for m in body["credential_matches"]:
        if m["registry"] in ("conf-c-ny", "conf-c-ca"):
            assert m["has_conflict"] is False
```

Apply the equivalent seeding swap to `test_contract.py`, `test_general_resolution.py`, and `test_flows.py` (read each file's current sync-based seeding first — same pattern: replace the `client.post("/api/v1/credential-matches", ...)` calls with `seed_employee(db, ...)` + `seed_credential_match(db, ...)`, replacing `cami_employee_id`→`employee_id`, `registry_prefix`/`registry`→`registry`, `params_credential_id`→`credential_id`, `check_date`→`date_updated`+`date_created`).

- [ ] **Step 6: Run the full rewritten set**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ttl.py tests/test_conflict.py tests/test_contract.py tests/test_general_resolution.py tests/test_flows.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/services/search.py tests/test_ttl.py tests/test_conflict.py tests/test_contract.py tests/test_general_resolution.py tests/test_flows.py
git commit -m "Rewrite search_credential/general_search against streamline_local"
```

---

### Task 4: Router/schema/main.py cleanup — remove sync + rebuild surface

**Files:**
- Delete: `C:\new-codes\golden-profile-service\app\routers\employees.py`, `credential_matches.py`, `exclusion_matches.py`
- Delete: `C:\new-codes\golden-profile-service\app\services\employee_sync.py`, `credential_sync.py`, `exclusion_sync.py`
- Modify: `C:\new-codes\golden-profile-service\app\routers\resolve.py` (drop `/rebuild`)
- Modify: `C:\new-codes\golden-profile-service\app\main.py` (drop the three deleted routers)
- Modify: `C:\new-codes\golden-profile-service\app\schemas.py` (delete now-unused sync schemas)
- Test: `C:\new-codes\golden-profile-service\tests\test_stats.py` (rewrite seeding)

**Interfaces:**
- Produces: `app.main:app` with exactly 3 routers (`search`, `resolve`, `stats`) plus the bare `/health` route.

- [ ] **Step 1: Delete the sync routers and services**

```bash
cd C:\new-codes\golden-profile-service
rm app/routers/employees.py app/routers/credential_matches.py app/routers/exclusion_matches.py
rm app/services/employee_sync.py app/services/credential_sync.py app/services/exclusion_sync.py
```

- [ ] **Step 2: Update resolve.py — drop the /rebuild route**

```python
# app/routers/resolve.py
"""Entity-resolution endpoint — unify records for one real person."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..security import require_api_key
from ..services import resolution as resolution_service

router = APIRouter(prefix="/api/v1/resolve", tags=["resolve"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=schemas.ResolveOut)
def resolve(payload: schemas.ResolveIn, db: Session = Depends(get_db)):
    """Resolve identifiers/name to a canonical person, computed live.

    A strong identifier (NPI, or registry + license number) or a high enough
    fuzzy name+DOB score merges every employee that reaches it, transitively.
    A name-only lookup returns candidates for review — it never merges."""
    return resolution_service.resolve(db, payload)


@router.post("/suggestions", response_model=schemas.ResolveSuggestionsOut)
def suggestions(payload: schemas.ResolveSuggestionsIn, db: Session = Depends(get_db)):
    """Review-only candidates in the score band below auto-merge — never
    merges; surfaces possible same-person records for a human to confirm."""
    return schemas.ResolveSuggestionsOut(
        params_first_name=payload.params_first_name,
        params_last_name=payload.params_last_name,
        suggestions=resolution_service.suggestions(
            db, payload.params_first_name, payload.params_last_name
        ),
    )


@router.get("/employee/{cami_employee_id}", response_model=schemas.ResolveOut)
def resolve_employee(cami_employee_id: int, db: Session = Depends(get_db)):
    """Canonical-group lookup for one employee, computed live on every call."""
    return resolution_service.resolve_employee(db, cami_employee_id)
```

- [ ] **Step 3: Update main.py**

```python
# app/main.py
"""FastAPI application entrypoint for the Golden Profile Service."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__
from .database import init_db
from .routers import resolve, search, stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Golden Profile Service",
    version=__version__,
    description=(
        "Reads employee, credential-match and exclusion-match data live from "
        "streamline_local and serves it as an alternative source of licensing "
        "data for CAMI credentialing searches. Read-only — no ingestion."
    ),
    lifespan=lifespan,
)

app.include_router(search.router)
app.include_router(resolve.router)
app.include_router(stats.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "version": __version__}
```

- [ ] **Step 4: Delete the now-unused sync schemas from schemas.py**

Delete these classes entirely from `app/schemas.py`: `NameIn`, `EntityNameIn`, `AddressIn`, `LicensingCredentialIn`, `IndividualSyncIn`, `EntitySyncIn`, `EmployeeSyncResult`, `CredentialResolutionIn`, `CredentialMatchSyncIn`, `CredentialMatchSyncResult`, `CredentialMatchBulkSyncIn`, `CredentialMatchBulkSyncResult`, `ExclusionActionIn`, `ExclusionMatchSyncIn`, `ExclusionMatchSyncResult`. Keep everything from `CredentialSearchIn` onward (search, resolve, general-search schemas) — those are unchanged.

- [ ] **Step 5: Start the app and confirm it boots clean**

Run: `.venv\Scripts\python.exe -c "from app.main import app; print(sorted(r.path for r in app.routes))"`
Expected output includes only: `/health`, `/api/v1/search/credential`, `/api/v1/search/general`, `/api/v1/resolve`, `/api/v1/resolve/suggestions`, `/api/v1/resolve/employee/{cami_employee_id}`, `/api/v1/stats` (plus FastAPI's built-in `/openapi.json`, `/docs`, `/redoc`).

- [ ] **Step 6: Rewrite test_stats.py seeding**

```python
# tests/test_stats.py
"""Observability: cache hit-rate and search counters."""
from tests.conftest import seed_credential_match, seed_employee


def test_stats_tracks_hit_and_miss(client, db):
    seed_employee(db, id=9700, first_name="Statz", last_name="Persony")
    seed_credential_match(
        db, employee_id=9700, registry="statsreg", credential_id="ST-1",
        status="VALID", match_summary_status="Valid", match="{}",
    )
    client.post("/api/v1/search/credential", json={
        "registry_prefix": "statsreg", "params_first_name": "Statz",
        "params_last_name": "Persony", "params_credential_id": "ST-1",
    })
    client.post("/api/v1/search/credential", json={
        "registry_prefix": "unknownreg", "params_first_name": "No", "params_last_name": "Body",
    })
    body = client.get("/api/v1/stats").json()
    assert body["counters"]["search.hit"] >= 1
    assert body["counters"]["search.miss"] >= 1
    assert body["derived"]["search_total"] >= 2
```

- [ ] **Step 7: Run the full test suite so far**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: PASS for every file rewritten in Tasks 1-4. Task 5 below handles the remaining stale test files.

- [ ] **Step 8: Commit**

```bash
git add app/main.py app/routers/resolve.py app/schemas.py tests/test_stats.py
git rm app/routers/employees.py app/routers/credential_matches.py app/routers/exclusion_matches.py
git rm app/services/employee_sync.py app/services/credential_sync.py app/services/exclusion_sync.py
git commit -m "Remove sync/ingest endpoints and the resolve/rebuild route"
```

---

### Task 5: Delete obsolete sync/persistence tests, finalize conftest.py

**Files:**
- Delete: `C:\new-codes\golden-profile-service\tests\test_bulk_sync.py`, `test_canonical_persist.py`, `test_hotpath_persisted.py`, `test_idempotent_credential_sync.py`, `test_no_match_skip.py`, `test_observability.py`
- Modify: `C:\new-codes\golden-profile-service\tests\conftest.py` (finalize seed helpers)

**Interfaces:**
- Produces: `tests.conftest.seed_employee(db, **cols) -> int`, `tests.conftest.seed_credential_match(db, **cols) -> int`, `tests.conftest.seed_exclusion_match(db, **cols) -> int` — every test file from Tasks 2-4 already depends on the first two; this task adds the third and is the final, stable version.

- [ ] **Step 1: Delete the obsolete test files (they test removed sync/persistence features)**

```bash
cd C:\new-codes\golden-profile-service
rm tests/test_bulk_sync.py tests/test_canonical_persist.py tests/test_hotpath_persisted.py
rm tests/test_idempotent_credential_sync.py tests/test_no_match_skip.py tests/test_observability.py
```

- [ ] **Step 2: Finalize conftest.py**

```python
# tests/conftest.py
"""Test fixtures: fresh temp SQLite DB shaped like streamline_local, auth disabled."""
import os
import tempfile
from datetime import date, datetime

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["API_KEYS"] = ""  # disable auth for tests
os.environ["VALID_MATCH_STATUSES"] = "VALID,ACTIVE"

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.streamline_schema import credential_matches, employees, exclusion_lists, exclusion_records, matches


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
    """Insert one employees row; returns its id.

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


def seed_exclusion_record(db, **kwargs):
    kwargs.setdefault("date_created", datetime(2026, 6, 1))
    result = db.execute(exclusion_records.insert().values(**kwargs))
    db.commit()
    return result.inserted_primary_key[0]


def seed_exclusion_list(db, **kwargs):
    result = db.execute(exclusion_lists.insert().values(**kwargs))
    db.commit()
    return result.inserted_primary_key[0]


def seed_exclusion_match(db, *, employee_id, prefix, description="Test Exclusion List", **kwargs):
    """Convenience: creates the exclusion_lists + exclusion_records rows too,
    then links them via `matches`. Returns the `matches.id`."""
    list_id = seed_exclusion_list(db, prefix=prefix, description=description)
    record_id = seed_exclusion_record(db, exclusion_list_prefix=prefix, match=kwargs.pop("match", "{}"))
    kwargs.setdefault("date_created", datetime(2026, 6, 1))
    result = db.execute(matches.insert().values(employee_id=employee_id, exclusion_record_id=record_id, **kwargs))
    db.commit()
    return result.inserted_primary_key[0]
```

- [ ] **Step 3: Run the entire suite**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: PASS, all files green — this is the full green baseline for the service.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git rm tests/test_bulk_sync.py tests/test_canonical_persist.py tests/test_hotpath_persisted.py
git rm tests/test_idempotent_credential_sync.py tests/test_no_match_skip.py tests/test_observability.py
git commit -m "Remove obsolete sync/persistence tests; finalize streamline_local test fixtures"
```

---

### Task 6: Client — remove sync plumbing, keep search-only gateway

**Files:**
- Delete: `C:\new-codes\client\app\Observers\GoldenProfile\CredentialMatchGoldenProfileObserver.php`
- Delete: `C:\new-codes\client\app\Listeners\GoldenProfile\SyncEmployeeToGoldenProfile.php`, `SyncExclusionMatchToGoldenProfile.php`
- Delete: `C:\new-codes\client\app\Jobs\GoldenProfile\PushToGoldenProfileJob.php`
- Delete: `C:\new-codes\client\app\Console\Commands\GoldenProfile\GoldenProfileReconcile.php`, `GoldenProfileWork.php`, `GoldenProfileRebuildGraph.php`
- Delete: `C:\new-codes\client\provision\ansible\roles\supervisor\templates\golden_profile_worker.conf.j2`
- Modify: `C:\new-codes\client\provision\ansible\roles\supervisor\tasks\main.yml`
- Modify: `C:\new-codes\client\app\Providers\EventServiceProvider.php`
- Modify: `C:\new-codes\client\app\Providers\GoldenProfileServiceProvider.php`
- Modify: `C:\new-codes\client\app\Services\GoldenProfile\GoldenProfileGateway.php`
- Modify: `C:\new-codes\client\app\Services\GoldenProfile\GoldenProfileClient.php`
- Modify: `C:\new-codes\client\config\services.php`
- Modify: `C:\new-codes\client\app\Http\Controllers\Json\Check\EmployeeController.php`
- Modify: `C:\new-codes\client\app\Http\Controllers\Check\ListController.php`

**Interfaces:**
- Produces: `GoldenProfileGateway::isSearchEnabled()`, `lookupCredentialData(CredentialMatch $credentialMatch): ?array` — the only public surface left; every other call site in the codebase must stop referencing `syncEmployee`/`syncCredentialMatch`/`syncExclusionMatch`/`isSyncEnabled`/`isQueueEnabled`/`getClient()`.

- [ ] **Step 1: Delete the sync-only files**

```bash
cd C:\new-codes\client
rm app/Observers/GoldenProfile/CredentialMatchGoldenProfileObserver.php
rm app/Listeners/GoldenProfile/SyncEmployeeToGoldenProfile.php
rm app/Listeners/GoldenProfile/SyncExclusionMatchToGoldenProfile.php
rm app/Jobs/GoldenProfile/PushToGoldenProfileJob.php
rm app/Console/Commands/GoldenProfile/GoldenProfileReconcile.php
rm app/Console/Commands/GoldenProfile/GoldenProfileWork.php
rm app/Console/Commands/GoldenProfile/GoldenProfileRebuildGraph.php
rm provision/ansible/roles/supervisor/templates/golden_profile_worker.conf.j2
rmdir app/Observers/GoldenProfile app/Listeners/GoldenProfile app/Jobs/GoldenProfile
```

- [ ] **Step 2: Remove the golden_profile_worker entry from supervisor's tasks/main.yml**

In `provision/ansible/roles/supervisor/tasks/main.yml`, find the block (around line 70-73):
```yaml
    - async_report_generator.conf
    - api_apploi_credential_matches.conf
    - api_single_transaction_credential_matches.conf
    - golden_profile_worker.conf
```
Delete the `- golden_profile_worker.conf` line only, leaving the other three entries.

- [ ] **Step 3: Update EventServiceProvider.php — drop the sync listener registrations and observer registrations**

Remove the imports:
```php
use App\Listeners\GoldenProfile\SyncEmployeeToGoldenProfile;
use App\Listeners\GoldenProfile\SyncExclusionMatchToGoldenProfile;
use App\Observers\GoldenProfile\CredentialMatchGoldenProfileObserver;
```

In the `$listen` array, revert these three event entries to just their non-GoldenProfile listeners:
```php
        EmployeeCreatedEvent::class => [
            CreateEmployeeListActiveHistoryCreatedRecord::class,
        ],

        EmployeeTerminatedEvent::class => [
            CreateEmployeeListActiveHistoryTerminatedRecord::class,
        ],

        EmployeeUpdatedEvent::class => [
            CheckEmployeeForInvalidMatchResolution::class,
        ],

        ExclusionMatchesConfirmedEvent::class => [
            UpdateEmployeeListMatchStatisticConfirmedRecord::class,
        ],

        ExclusionMatchesResolvedEvent::class => [
            EmployeeVerificationNoteDeleter::class,
            UpdateEmployeeListMatchStatisticResolvedRecord::class,
        ],
```

Note `EmployeeUpdatedEvent::class` appears twice in the original file (lines 75-77 and 99-102) — both listed the same `CheckEmployeeForInvalidMatchResolution::class` plus one had `SyncEmployeeToGoldenProfile::class`. Laravel merges array keys, so consolidate to a single `EmployeeUpdatedEvent::class => [CheckEmployeeForInvalidMatchResolution::class]` entry if the duplication was only there for the sync listener; otherwise keep both non-GoldenProfile entries as they were.

Replace the `boot()` method body (drop both `observe()` calls and their explanatory comment, and the now-unused `CredentialMatch`/`CredentialMatchFromCommand` imports if nothing else in the file uses them — check first with a search for other usages before removing those two imports):

```php
    /**
     * Register any events for your application.
     *
     * @return void
     */
    public function boot()
    {
    }
```

- [ ] **Step 4: Update GoldenProfileServiceProvider.php — drop the GoldenProfileWork binding**

```php
<?php

namespace App\Providers;

use App\Services\GoldenProfile\GoldenProfileClient;
use App\Services\GoldenProfile\GoldenProfileGateway;
use Illuminate\Contracts\Support\DeferrableProvider;
use Illuminate\Foundation\Application;
use Illuminate\Support\ServiceProvider;

class GoldenProfileServiceProvider extends ServiceProvider implements DeferrableProvider
{
    /**
     * Register services.
     */
    public function register(): void
    {
        $this->app->singleton('service.golden_profile.client', function (Application $app) {
            return new GoldenProfileClient(
                (string) config('services.golden-profile.url'),
                (string) config('services.golden-profile.key'),
                $app['logger.general'],
                (float) config('services.golden-profile.timeout', 5)
            );
        });

        $this->app->singleton('service.golden_profile', function (Application $app) {
            return new GoldenProfileGateway(
                $app['service.golden_profile.client'],
                $app['logger.general'],
                (bool) config('services.golden-profile.search_enabled', false)
            );
        });
    }

    public function provides()
    {
        return [
            'service.golden_profile',
            'service.golden_profile.client',
        ];
    }
}
```

- [ ] **Step 5: Rewrite GoldenProfileGateway.php — search-only**

```php
<?php

namespace App\Services\GoldenProfile;

use Psr\Log\LoggerInterface;
use Streamlineverify\SV\CredentialMatch\CredentialMatch;
use Throwable;

/**
 * Maps StreamlineVerify domain models onto Golden Profile Service requests and
 * drives credentialing search (search-before-scrape).
 *
 * The Golden Profile Service now queries streamline_local directly — there is
 * nothing left to sync. This gateway is search-only. Fail-safe: returns null
 * on any error so the Golden Profile can never break a CAMI flow.
 *
 * PII note: no data is sent to the service; searches use only name/registry/
 * credential-id parameters already known to CAMI.
 */
class GoldenProfileGateway
{
    private GoldenProfileClient $client;
    private LoggerInterface $logger;
    private bool $searchEnabled;

    public function __construct(
        GoldenProfileClient $client,
        LoggerInterface $logger,
        bool $searchEnabled
    ) {
        $this->client = $client;
        $this->logger = $logger;
        $this->searchEnabled = $searchEnabled;
    }

    public function isSearchEnabled(): bool
    {
        return $this->searchEnabled;
    }

    /**
     * Return a cached scraper-shaped result the caller can apply instead of
     * scraping, or null to proceed with the scrape.
     */
    public function lookupCredentialData(CredentialMatch $credentialMatch): ?array
    {
        if (! $this->searchEnabled) {
            return null;
        }

        try {
            $employee = $this->attr($credentialMatch, 'employee');
            $firstName = $employee ? trim((string) $this->attr($employee, 'first_name')) : '';
            $lastName = $employee ? trim((string) $this->attr($employee, 'last_name')) : '';

            if ($firstName === '' || $lastName === '') {
                return null;
            }

            $result = $this->client->searchCredential(array_filter([
                'registry_prefix' => strtolower((string) $this->attr($credentialMatch, 'registry')),
                'params_credential_id' => (string) $this->attr($credentialMatch, 'credential_id'),
                'params_license_type' => (string) $this->attr($credentialMatch, 'license_type_id'),
                'params_first_name' => $firstName,
                'params_last_name' => $lastName,
                'cami_employee_id' => (int) $this->attr($credentialMatch, 'employee_id'),
            ], fn ($v) => $v !== null && $v !== ''));

            if (! is_array($result) || empty($result['found'])) {
                $this->logMiss($credentialMatch, $result['reason'] ?? 'no usable cached result');

                return null;
            }

            $action = $result['action'] ?? null;
            if (! in_array($action, ['return_result', 'auto_resolve_name_mismatch'], true)) {
                $this->logMiss($credentialMatch, 'action='.(string) $action);

                return null;
            }

            $encodedMatch = $result['credential_match']['match'] ?? null;
            $data = is_string($encodedMatch) ? json_decode($encodedMatch, true) : $encodedMatch;

            if (is_array($data) && array_key_exists('response_code', $data)) {
                $ageNote = isset($result['age_days']) ? ', age '.$result['age_days'].'d' : '';
                $this->logger->info('[GoldenProfile] cache hit ('.$action.$ageNote.') for credential match '
                    .$this->attr($credentialMatch, 'id'));

                return $data;
            }

            $this->logMiss($credentialMatch, 'cached match not scraper-shaped');

            return null;
        } catch (Throwable $e) {
            $this->logger->error('[GoldenProfile] lookupCredentialData failed for match '
                .$this->attr($credentialMatch, 'id').': '.$e->getMessage());

            return null;
        }
    }

    private function logMiss(CredentialMatch $credentialMatch, string $reason): void
    {
        $this->logger->info('[GoldenProfile] cache miss ('.$reason.') for credential match '
            .$this->attr($credentialMatch, 'id'));
    }

    private function attr($model, string $key)
    {
        try {
            return $model->{$key} ?? null;
        } catch (Throwable $e) {
            return null;
        }
    }
}
```

Note: the search result no longer carries a `from_golden_profile` marker requirement — since nothing re-syncs it, the loop-prevention marker (`MATCH_SOURCE_KEY`/`isGoldenProfileResult()`) is dead code and is deliberately dropped along with the sync gate that used it.

- [ ] **Step 6: Rewrite GoldenProfileClient.php — search-only HTTP methods**

```php
<?php

namespace App\Services\GoldenProfile;

use GuzzleHttp\Client;
use GuzzleHttp\ClientInterface;
use Psr\Log\LoggerInterface;
use Throwable;

/**
 * Thin HTTP client for the Golden Profile Service's search API.
 *
 * Fail-safe: network/HTTP/decoding errors are logged and turned into a null
 * return so the Golden Profile can never break a CAMI flow.
 */
class GoldenProfileClient
{
    private ClientInterface $http;
    private string $apiKey;
    private LoggerInterface $logger;

    public function __construct(
        string $baseUrl,
        string $apiKey,
        LoggerInterface $logger,
        float $timeout = 5.0,
        ?ClientInterface $http = null
    ) {
        $this->apiKey = $apiKey;
        $this->logger = $logger;
        $this->http = $http ?? new Client([
            'base_uri' => rtrim($baseUrl, '/').'/',
            'timeout' => $timeout,
            'connect_timeout' => $timeout,
        ]);
    }

    /**
     * Ask the Golden Profile whether it can answer a credentialing check.
     *
     * @return array|null The decoded search result
     *                    ({found, action, credential_match, resolution, ...}),
     *                    or null on any error.
     */
    public function searchCredential(array $payload): ?array
    {
        return $this->post('api/v1/search/credential', $payload);
    }

    private function post(string $path, array $payload): ?array
    {
        try {
            $response = $this->http->request('POST', $path, [
                'headers' => [
                    'X-API-Key' => $this->apiKey,
                    'Accept' => 'application/json',
                ],
                'json' => $payload,
                'http_errors' => false,
            ]);

            $status = $response->getStatusCode();
            $body = (string) $response->getBody();

            if ($status >= 400) {
                $this->logger->warning('[GoldenProfile] '.$path.' returned HTTP '.$status.': '.$body);

                return null;
            }

            $decoded = json_decode($body, true);

            return is_array($decoded) ? $decoded : null;
        } catch (Throwable $e) {
            $this->logger->error('[GoldenProfile] '.$path.' request failed: '.$e->getMessage());

            return null;
        }
    }
}
```

- [ ] **Step 7: Update config/services.php — drop sync/queue config keys**

```php
    'golden-profile' => [
        'url' => env('GOLDEN_PROFILE_BASE_URL'),
        'key' => env('GOLDEN_PROFILE_API_KEY'),
        'timeout' => (float) env('GOLDEN_PROFILE_TIMEOUT', 5),
        // Consult the Golden Profile before triggering a bot scrape.
        'search_enabled' => (bool) env('GOLDEN_PROFILE_SEARCH_ENABLED', false),
    ],
];
```

- [ ] **Step 8: Remove the syncEmployee block from EmployeeController.php**

In `app/Http/Controllers/Json/Check/EmployeeController.php`, delete lines 411-425 (the `try { $goldenProfile = app('service.golden_profile'); ... }` block inside `updateCredentialMatches()`), leaving:

```php
                /** @var Employee $employee */
                $employee = Employee::find($employeeId);

                $credentialMatches = $this->checkedEmployeeService->getEmployeeCredentialMatches($employee);
```

Leave the `lookupCredentialData()` block (around line 566-586) untouched — that's the search path we're keeping.

- [ ] **Step 9: Remove syncListEmployeesToGoldenProfile from ListController.php**

In `app/Http/Controllers/Check/ListController.php`:
1. Delete the call site (around line 147): remove `$this->syncListEmployeesToGoldenProfile($employeeList);` and its preceding comment block (lines 143-147).
2. Delete the entire private method `syncListEmployeesToGoldenProfile()` (lines ~223-253).

- [ ] **Step 10: Search for any remaining references to removed symbols**

Run: `grep -rn "syncEmployee\|syncCredentialMatch\|syncExclusionMatch\|isSyncEnabled\|isQueueEnabled\|getClient()\|GoldenProfileWork\|PushToGoldenProfileJob\|SyncEmployeeToGoldenProfile\|SyncExclusionMatchToGoldenProfile\|CredentialMatchGoldenProfileObserver\|rebuildCanonicalGraph\|MATCH_SOURCE_KEY\|isGoldenProfileResult" app/ config/ provision/`
Expected: no output (empty). If anything remains, remove or update that call site before continuing.

- [ ] **Step 11: Commit**

```bash
cd C:\new-codes\client
git add -A app/Providers/EventServiceProvider.php app/Providers/GoldenProfileServiceProvider.php
git add app/Services/GoldenProfile/GoldenProfileGateway.php app/Services/GoldenProfile/GoldenProfileClient.php
git add config/services.php app/Http/Controllers/Json/Check/EmployeeController.php app/Http/Controllers/Check/ListController.php
git add provision/ansible/roles/supervisor/tasks/main.yml
git rm -r app/Observers/GoldenProfile app/Listeners/GoldenProfile app/Jobs/GoldenProfile
git rm app/Console/Commands/GoldenProfile/GoldenProfileReconcile.php app/Console/Commands/GoldenProfile/GoldenProfileWork.php app/Console/Commands/GoldenProfile/GoldenProfileRebuildGraph.php
git rm provision/ansible/roles/supervisor/templates/golden_profile_worker.conf.j2
git commit -m "Remove Golden Profile sync/ingest plumbing; keep search-only gateway"
```

**Manual follow-up (not code, flag to the user — do not attempt from this task):** the `golden-profile:rebuild-graph` scheduled command was inserted as DB rows in the VM's `commands`/`commands_schedules` tables (command id 13, hourly), per prior session notes — not in code. Deleting the command class does not remove that schedule row. Whoever runs this plan against the VM should also delete that scheduled-command row (or it will fail every hour trying to invoke a command that no longer exists).

---

### Task 7: Client PHPUnit test cleanup

**Files:**
- Find and delete: any PHPUnit test file under `tests/unit/Service/GoldenProfile/` (or wherever they live) that tests `CredentialMatchGoldenProfileObserver`, `SyncEmployeeToGoldenProfile`, `SyncExclusionMatchToGoldenProfile`, `PushToGoldenProfileJob`, `GoldenProfileReconcile`, `GoldenProfileWork`, `GoldenProfileRebuildGraph`, or `GoldenProfileGateway`'s sync methods.
- Keep/update: tests for `GoldenProfileGateway::lookupCredentialData()` and `GoldenProfileClient::searchCredential()`.

**Interfaces:**
- Consumes: the rewritten `GoldenProfileGateway`/`GoldenProfileClient` from Task 6.

- [ ] **Step 1: Locate every existing Golden Profile PHPUnit test file**

Run: `cd C:\new-codes\client && grep -rl "GoldenProfile" tests/unit/ tests/ 2>/dev/null`

- [ ] **Step 2: For each file found, classify and act**

For each file returned by Step 1: open it and check what class it tests (via its `use` statements / the class name under test).
- If it tests a class deleted in Task 6 (`CredentialMatchGoldenProfileObserver`, `SyncEmployeeToGoldenProfile`, `SyncExclusionMatchToGoldenProfile`, `PushToGoldenProfileJob`, `GoldenProfileReconcile`, `GoldenProfileWork`, `GoldenProfileRebuildGraph`), delete the file.
- If it tests `GoldenProfileGateway` or `GoldenProfileClient`: keep the file, but delete every test method that calls a removed method (`syncEmployee`, `syncCredentialMatch`, `syncExclusionMatch`, `syncCredentialMatchesBulk`, `buildIndividualPayload`, `buildEntityPayload`, `dispatchJob`, `isSyncEnabled`, `isQueueEnabled`, `getClient`, `rebuildCanonicalGraph`). Keep every test method that calls `lookupCredentialData`/`searchCredential`/`isSearchEnabled` unchanged — their behavior did not change in Task 6, only the sync methods around them were removed.

- [ ] **Step 3: Run the Golden Profile PHPUnit suite**

Run: `cd C:\new-codes\client && php vendor/bin/phpunit --no-coverage --filter GoldenProfile`
Expected: PASS, 0 failures, 0 errors, 0 skipped (a skip means a leftover reference to a deleted class was not cleaned up).

- [ ] **Step 4: Commit**

```bash
cd C:\new-codes\client
git add -A tests/
git commit -m "Remove Golden Profile sync tests; keep search-only gateway/client coverage"
```

---

### Task 8: Explorer — point at streamline_local, rewrite queries.py

**Files:**
- Modify: `C:\new-codes\golden-profile-explorer\app\db.py`
- Modify: `C:\new-codes\golden-profile-explorer\app\queries.py` (full rewrite)

**Interfaces:**
- Produces: `queries.search_profiles(first_name, last_name, credential_id="", npi="", page=1, page_size=25) -> dict` — same return shape (`identities`, `suggestions`, `total`, `page`, etc.) as before; `app/main.py`'s `/api/search` route is unchanged and keeps calling this with the same signature.
- Produces: `queries.overview_stats() -> dict` — same keys as before, now counting real tables (`employees`, `credential_matches`, `matches`, `exclusion_records`, `credential_match_resolutions`, `match_actions`).

- [ ] **Step 1: Update db.py's default URL**

```python
# app/db.py — change only this line
_DEFAULT_URL = "mysql+pymysql://root:root@127.0.0.1:33066/streamline_local"
```

(Everything else in `db.py` — the `.env` resolution order, `_SERVICE_ENV` pointing at the sibling service's `.env` — is unchanged; the service's `.env` will also point at `streamline_local` after Task 1, so this still "just works" alongside it.)

- [ ] **Step 2: Rewrite queries.py against the real schema**

This mirrors `golden-profile-service/app/services/resolution.py`'s scoring model (Task 2), independently — the Explorer stays decoupled (DB-direct, no service API call), so the scoring logic is duplicated here rather than imported.

```python
"""Read-only queries against the real streamline_local schema.

Employees are a single flat table (individual vs. entity distinguished by a
non-empty `business` column); there is no separate individuals/entities
split, no licensing_credentials table, and exclusion matches are linked via
`matches` (employee_id + exclusion_record_id), not a mirror-only
exclusion_matches table.

Canonical-identity grouping mirrors the service's resolution.py scoring model
(SSN/TIN hash or NPI exact match = 1.0, shared registry+credential_id = 0.9,
name similarity*0.5 + DOB match*0.4 otherwise) — duplicated here on purpose
since the Explorer is intentionally decoupled from the service.
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.engine import Connection

from .db import engine

_TABLES: set[str] = set(inspect(engine).get_table_names())
_JSON_COLUMNS = {"match"}

PAGE_SIZE_DEFAULT = 25
PAGE_SIZE_MAX = 100
MAX_IDS = 5000
MAX_SECTION_ROWS = 200

_VALID_STATUSES = {"VALID", "ACTIVE", "CLEAR", "PASS", "VERIFIED"}
MERGE_THRESHOLD = 0.85
SUGGEST_THRESHOLD = 0.5

_DIMINUTIVES = {
    ("robert", "bob"), ("robert", "rob"), ("william", "bill"), ("william", "will"),
    ("richard", "rick"), ("richard", "dick"), ("michael", "mike"), ("james", "jim"),
    ("katherine", "kathy"), ("katherine", "kate"), ("elizabeth", "liz"),
    ("elizabeth", "beth"), ("margaret", "peggy"), ("charles", "chuck"),
    ("thomas", "tom"), ("joseph", "joe"), ("john", "jack"), ("daniel", "dan"),
}


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #
def _cell(key: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, Decimal):
        return float(value)
    if key in _JSON_COLUMNS and isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def _row(mapping) -> dict[str, Any]:
    return {k: _cell(k, v) for k, v in dict(mapping).items() if k != "_rn"}


def _rows(result) -> list[dict[str, Any]]:
    return [_row(m) for m in result.mappings()]


def _like(value: str | None) -> str | None:
    value = (value or "").strip()
    return f"{value}%" if value else None


def _in_query(sql: str, ids: list[int]) -> Any:
    return text(sql).bindparams(bindparam("ids", expanding=True))


def _group(rows: list[dict], key: str) -> dict[Any, list[dict]]:
    out: dict[Any, list[dict]] = defaultdict(list)
    for r in rows:
        out[r.get(key)].append(r)
    return out


def _norm(value: str | None) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


# --------------------------------------------------------------------------- #
# Employee-id discovery
# --------------------------------------------------------------------------- #
_ALT_NAME_COLS = [(f"alt_first_name_{i}", f"alt_last_name_{i}") for i in range(1, 6)]


def _name_ids(c: Connection, first: str, last: str) -> set[int]:
    """Employee ids matching first AND last name — primary name or any AKA slot."""
    fp, lp = _like(first), _like(last)
    if fp is None and lp is None:
        return set()
    clauses = []
    for fcol, lcol in [("first_name", "last_name"), *_ALT_NAME_COLS]:
        pair = []
        if fp is not None:
            pair.append(f"{fcol} LIKE :fp")
        if lp is not None:
            pair.append(f"{lcol} LIKE :lp")
        clauses.append(" AND ".join(pair) or "1=1")
    sql = text(f"SELECT DISTINCT id FROM employees WHERE {' OR '.join(f'({c})' for c in clauses)}")
    params: dict[str, str] = {}
    if fp is not None:
        params["fp"] = fp
    if lp is not None:
        params["lp"] = lp
    return {r[0] for r in c.execute(sql, params) if r[0] is not None}


def _credential_ids(c: Connection, credential_id: str) -> set[int]:
    cp = _like(credential_id)
    ids: set[int] = set()
    sql = text("SELECT DISTINCT employee_id FROM credential_matches WHERE credential_id LIKE :cp")
    ids.update(r[0] for r in c.execute(sql, {"cp": cp}) if r[0] is not None)
    sql2 = text("SELECT DISTINCT id FROM employees WHERE certification_number LIKE :cp")
    ids.update(r[0] for r in c.execute(sql2, {"cp": cp}) if r[0] is not None)
    return ids


def _npi_ids(c: Connection, npi: str, scope: set[int]) -> set[int]:
    digits = _digits(npi)
    ids: set[int] = set()
    if not digits:
        return ids
    sql = text("SELECT DISTINCT id FROM employees WHERE npi = :npi")
    ids.update(r[0] for r in c.execute(sql, {"npi": int(digits)}) if r[0] is not None)
    if engine.dialect.name == "mysql" and scope:
        sql2 = _in_query(
            "SELECT DISTINCT employee_id FROM credential_matches "
            "WHERE employee_id IN :ids AND JSON_VALID(`match`) "
            "AND JSON_UNQUOTE(JSON_EXTRACT(`match`, '$.npi')) = :npi", list(scope))
        ids.update(r[0] for r in c.execute(sql2, {"ids": list(scope), "npi": digits}) if r[0] is not None)
    return ids


def _matching_employee_ids(c: Connection, first: str, last: str, credential_id: str, npi: str) -> list[int]:
    candidates = _name_ids(c, first, last)
    if candidates and _like(credential_id) is not None:
        candidates &= _credential_ids(c, credential_id)
    if candidates and (npi or "").strip():
        candidates &= _npi_ids(c, npi, candidates)
    return sorted(candidates)


# --------------------------------------------------------------------------- #
# Scoring / canonical grouping (mirrors service resolution.py)
# --------------------------------------------------------------------------- #
def _first_name_score(a: str, b: str) -> tuple[float, str]:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0, ""
    if a == b:
        return 0.95, "same name"
    lo, hi = sorted((a, b), key=len)
    if len(lo) == 1 and hi.startswith(lo):
        return 0.6, "initial matches"
    if len(lo) >= 2 and hi.startswith(lo):
        return 0.85, "one name is a prefix of the other"
    if (a, b) in _DIMINUTIVES or (b, a) in _DIMINUTIVES:
        return 0.9, "known nickname"
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    if ratio >= 0.8:
        return round(ratio, 2), "spelling is close"
    return 0.0, ""


def _npi_from_match(raw) -> str | None:
    try:
        data = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return None
    if isinstance(data, dict):
        d = _digits(data.get("npi"))
        return d or None
    return None


def _employee_keys(c: Connection, ids: list[int]) -> dict[int, dict]:
    """Per-employee scoring inputs: first/last/dob/ssn_hash/npi/licenses."""
    keys: dict[int, dict] = {}
    if not ids:
        return keys
    rows = c.execute(_in_query(
        "SELECT id, first_name, last_name, date_of_birth, ssn_hash, npi "
        "FROM employees WHERE id IN :ids", ids), {"ids": ids})
    for eid, first, last, dob, ssn_hash, npi in rows:
        keys[eid] = {
            "first": first or "", "last": last or "", "dob": dob,
            "ssn_hash": ssn_hash or None, "npi": _digits(npi) or None, "licenses": set(),
        }
    cm_rows = c.execute(_in_query(
        "SELECT employee_id, registry, credential_id, `match` FROM credential_matches "
        "WHERE employee_id IN :ids", ids), {"ids": ids})
    for eid, registry, cred_id, match in cm_rows:
        k = keys.setdefault(eid, {"first": "", "last": "", "dob": None, "ssn_hash": None, "npi": None, "licenses": set()})
        if registry and cred_id:
            k["licenses"].add(f"{str(registry).strip().lower()}:{str(cred_id).strip()}")
        if not k["npi"]:
            npi = _npi_from_match(match)
            if npi:
                k["npi"] = npi
    return keys


def _score_pair(a: dict, b: dict) -> float:
    if a["ssn_hash"] and a["ssn_hash"] == b["ssn_hash"]:
        return 1.0
    if a["npi"] and a["npi"] == b["npi"]:
        return 1.0
    if a["licenses"] & b["licenses"]:
        return 0.9
    if _norm(a["last"]) != _norm(b["last"]):
        return 0.0
    name_score, _ = _first_name_score(a["first"], b["first"])
    if name_score <= 0:
        return 0.0
    dob_match = bool(a["dob"] and b["dob"] and a["dob"] == b["dob"])
    return min(1.0, name_score * 0.5 + (0.4 if dob_match else 0.0))


def _canonical_map(c: Connection, ids: list[int]) -> dict[int, int]:
    """Union-find over the candidate set using the scored pairwise closure."""
    if not ids:
        return {}
    keys = _employee_keys(c, ids)
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    sorted_ids = sorted(ids)
    for i, a_id in enumerate(sorted_ids):
        for b_id in sorted_ids[i + 1:]:
            if a_id not in keys or b_id not in keys:
                continue
            if _score_pair(keys[a_id], keys[b_id]) >= MERGE_THRESHOLD:
                union(a_id, b_id)
    return {i: find(i) for i in ids}


def _suggestions(c: Connection, first: str, last: str, exclude: set[int]) -> list[dict]:
    """Review-only candidates: score in [SUGGEST_THRESHOLD, MERGE_THRESHOLD)."""
    first, last = (first or "").strip(), (last or "").strip()
    if not first or not last:
        return []
    rows = c.execute(text("SELECT DISTINCT id, first_name, last_name FROM employees WHERE last_name = :last"),
                     {"last": last})
    cand = [(eid, f, l) for eid, f, l in rows if eid is not None and eid not in exclude]
    if not cand:
        return []
    all_ids = list(exclude | {e for e, _, _ in cand})
    keys = _employee_keys(c, all_ids)
    query_key = {"first": first, "last": last, "dob": None, "ssn_hash": None, "npi": None, "licenses": set()}
    for e in exclude:
        k = keys.get(e)
        if k:
            query_key["ssn_hash"] = query_key["ssn_hash"] or k["ssn_hash"]
            query_key["npi"] = query_key["npi"] or k["npi"]
            query_key["licenses"] |= k["licenses"]

    best: dict[int, dict] = {}
    for eid, cand_first, cand_last in cand:
        k = keys.get(eid)
        if not k:
            continue
        score = _score_pair(query_key, k)
        if score < SUGGEST_THRESHOLD or score >= MERGE_THRESHOLD:
            continue
        name_score, reason = _first_name_score(first, cand_first or "")
        if eid not in best or score > best[eid]["score"]:
            best[eid] = {"cami_employee_id": eid, "first_name": cand_first,
                         "last_name": cand_last, "score": score, "reason": reason}
    return sorted(best.values(), key=lambda s: s["score"], reverse=True)[:25]


def _conflict_set(c: Connection, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    rows = c.execute(_in_query(
        "SELECT employee_id, registry, credential_id, status, match_summary_status "
        "FROM credential_matches WHERE employee_id IN :ids", ids), {"ids": ids})
    seen: dict[tuple, set[bool]] = defaultdict(set)
    for emp, reg, cred, status, summary in rows:
        valid = (str(status or "").upper() in _VALID_STATUSES or str(summary or "").upper() in _VALID_STATUSES)
        seen[(emp, reg, cred)].add(valid)
    return {emp for (emp, _, _), vals in seen.items() if True in vals and False in vals}


# --------------------------------------------------------------------------- #
# Batched per-page assembly
# --------------------------------------------------------------------------- #
def _assemble(c: Connection, ids: list[int]) -> list[dict]:
    if not ids:
        return []

    emps = _rows(c.execute(_in_query("SELECT * FROM employees WHERE id IN :ids", ids), {"ids": ids}))
    emp_by_id = {e["id"]: e for e in emps}

    cm_by_emp: dict[int, list[dict]] = defaultdict(list)
    cm_total: dict[int, int] = defaultdict(int)
    cms = _rows(c.execute(_in_query(
        "SELECT * FROM (SELECT *, ROW_NUMBER() OVER ("
        "  PARTITION BY employee_id, registry, credential_id"
        "  ORDER BY (date_updated IS NULL), date_updated DESC, id DESC) AS _rn"
        " FROM credential_matches WHERE employee_id IN :ids) ranked"
        " WHERE _rn = 1"
        " ORDER BY employee_id, (date_updated IS NULL), date_updated DESC, id DESC", ids),
        {"ids": ids}))
    kept_cm_ids: list[int] = []
    for cm in cms:
        emp = cm["employee_id"]
        cm_total[emp] += 1
        if len(cm_by_emp[emp]) >= MAX_SECTION_ROWS:
            continue
        cm["resolutions"] = []
        cm_by_emp[emp].append(cm)
        kept_cm_ids.append(cm["id"])
    if kept_cm_ids:
        by_cm = _group(_rows(c.execute(_in_query(
            "SELECT * FROM credential_match_resolutions WHERE credential_match_id IN :ids "
            "ORDER BY id DESC", kept_cm_ids), {"ids": kept_cm_ids})), "credential_match_id")
        for rows in cm_by_emp.values():
            for cm in rows:
                cm["resolutions"] = by_cm.get(cm["id"], [])

    em_by_emp: dict[int, list[dict]] = defaultdict(list)
    em_total: dict[int, int] = defaultdict(int)
    ems = _rows(c.execute(_in_query(
        "SELECT m.*, er.exclusion_list_prefix AS prefix, er.match AS exclusion_match "
        "FROM matches m JOIN exclusion_records er ON er.id = m.exclusion_record_id "
        "WHERE m.employee_id IN :ids ORDER BY m.employee_id, m.id DESC", ids), {"ids": ids}))
    kept_em_ids: list[int] = []
    for em in ems:
        emp = em["employee_id"]
        em_total[emp] += 1
        if len(em_by_emp[emp]) >= MAX_SECTION_ROWS:
            continue
        em["actions"] = []
        em_by_emp[emp].append(em)
        kept_em_ids.append(em["id"])
    if kept_em_ids:
        by_em = _group(_rows(c.execute(_in_query(
            "SELECT * FROM match_actions WHERE match_id IN :ids ORDER BY id DESC", kept_em_ids),
            {"ids": kept_em_ids})), "match_id")
        for rows in em_by_emp.values():
            for em in rows:
                em["actions"] = by_em.get(em["id"], [])

    canonical = _canonical_map(c, ids)
    conflicts = _conflict_set(c, ids)

    out = []
    for eid in ids:
        emp = emp_by_id.get(eid, {"id": eid})
        record = {
            "cami_employee_id": eid,
            "canonical_id": canonical.get(eid, eid),
            "has_conflict": eid in conflicts,
            "employee": emp,
            "is_entity": bool(emp.get("business")),
            "credential_matches": cm_by_emp.get(eid, []),
            "credential_matches_total": cm_total.get(eid, 0),
            "exclusion_matches": em_by_emp.get(eid, []),
            "exclusion_matches_total": em_total.get(eid, 0),
        }
        record["display_name"] = _display_name(record)
        out.append(record)
    return out


def _display_name(record: dict) -> str:
    emp = record["employee"]
    if emp.get("business"):
        return str(emp["business"])
    full = " ".join(x for x in (emp.get("first_name"), emp.get("last_name")) if x).strip()
    if full:
        return full
    return f"Employee #{record['cami_employee_id']}"


# --------------------------------------------------------------------------- #
# Identity consolidation
# --------------------------------------------------------------------------- #
def _members_of_canonical(canonical_ids: list[int], seed_canon: dict[int, int]) -> list[int]:
    wanted = set(canonical_ids)
    return sorted(emp for emp, cid in seed_canon.items() if cid in wanted)


def _match_sort_key(cm: dict) -> tuple:
    return (cm.get("date_updated") or "", cm.get("id") or 0)


def _conflict_keys(creds: list[dict]) -> set[tuple]:
    seen: dict[tuple, set[bool]] = defaultdict(set)
    for cm in creds:
        valid = str(cm.get("status") or cm.get("match_summary_status") or "").upper() in _VALID_STATUSES
        seen[(cm.get("registry"), cm.get("credential_id"))].add(valid)
    return {k for k, vals in seen.items() if True in vals and False in vals}


def _consolidate(members: list[dict], cid: int) -> dict:
    names: list[str] = []
    seen_names: set[str] = set()

    def _add_name(full: str) -> None:
        full = (full or "").strip()
        if full and full.lower() not in seen_names:
            seen_names.add(full.lower())
            names.append(full)

    npis: set[str] = set()
    dobs: set[str] = set()
    ssn_last_four: set[str] = set()
    has_ssn_hash = False
    licenses: dict[tuple, dict] = {}
    creds_all: list[dict] = []
    excls_all: list[dict] = []
    member_ids: list[int] = []
    is_entity = False
    employees_all: list[dict] = []

    for m in members:
        member_ids.append(m["cami_employee_id"])
        emp = m["employee"]
        employees_all.append(emp)
        if emp.get("business"):
            is_entity = True
            _add_name(emp["business"])
        else:
            _add_name(" ".join(x for x in (emp.get("first_name"), emp.get("last_name")) if x))
        for i in range(1, 6):
            _add_name(" ".join(x for x in (emp.get(f"alt_first_name_{i}"), emp.get(f"alt_last_name_{i}")) if x))
        if emp.get("npi"):
            npis.add(_digits(emp["npi"]))
        if emp.get("date_of_birth"):
            dobs.add(str(emp["date_of_birth"]))
        if emp.get("ssn_last_four"):
            ssn_last_four.add(str(emp["ssn_last_four"]))
        if emp.get("ssn_hash"):
            has_ssn_hash = True
        if emp.get("certification_number"):
            licenses[(emp["certification_number"], emp.get("certification_state"))] = {
                "number": emp["certification_number"], "state": emp.get("certification_state"),
                "type": emp.get("license_type" ) if "license_type" in emp else None,
            }
        for cm in m["credential_matches"]:
            creds_all.append(cm)
            match = cm.get("match")
            if isinstance(match, dict) and match.get("npi"):
                npis.add(_digits(match["npi"]))
        for em in m["exclusion_matches"]:
            excls_all.append(em)

    conflict_keys = _conflict_keys(creds_all)
    cred_latest: dict[tuple, dict] = {}
    for cm in creds_all:
        key = (cm.get("registry"), cm.get("credential_id"))
        if key not in cred_latest or _match_sort_key(cm) > _match_sort_key(cred_latest[key]):
            cred_latest[key] = cm
    credential_matches_out = sorted(cred_latest.values(), key=lambda cm: (cm.get("registry") or ""))
    for cm in credential_matches_out:
        cm["has_conflict"] = (cm.get("registry"), cm.get("credential_id")) in conflict_keys

    excl_latest: dict[str, dict] = {}
    for em in excls_all:
        key = em.get("prefix")
        if key not in excl_latest or (em.get("id") or 0) > (excl_latest[key].get("id") or 0):
            excl_latest[key] = em
    exclusion_matches_out = list(excl_latest.values())

    display_name = names[0] if names else f"Identity #{cid}"
    return {
        "identity_id": cid,
        "display_name": display_name,
        "is_entity": is_entity,
        "member_employee_ids": sorted(member_ids),
        "source_count": len(member_ids),
        "names": names,
        "identifiers": {
            "npi": sorted(n for n in npis if n),
            "dob": sorted(dobs),
            "ssn_last_four": sorted(ssn_last_four),
            "has_ssn_hash": has_ssn_hash,
            "licenses": list(licenses.values()),
        },
        "employees": employees_all,
        "credential_matches": credential_matches_out,
        "exclusion_matches": exclusion_matches_out,
        "has_conflict": bool(conflict_keys),
    }


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def search_profiles(
    first_name: str, last_name: str, credential_id: str = "", npi: str = "",
    page: int = 1, page_size: int = PAGE_SIZE_DEFAULT,
) -> dict[str, Any]:
    first, last = (first_name or "").strip(), (last_name or "").strip()
    cred = (credential_id or "").strip()
    npi = (npi or "").strip()
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or PAGE_SIZE_DEFAULT), PAGE_SIZE_MAX))

    result: dict[str, Any] = {
        "query": {"first_name": first, "last_name": last, "credential_id": cred, "npi": npi},
        "database": _redacted_url(),
        "page": page, "page_size": page_size, "total": 0, "count": 0,
        "has_more": False, "capped": False, "identities": [], "suggestions": [],
    }
    if not first or not last:
        result["error"] = "First and last name are both required."
        return result

    with engine.connect() as c:
        seed_ids = _matching_employee_ids(c, first, last, cred, npi)[:MAX_IDS]
        seed_canon = _canonical_map(c, seed_ids)
        identity_ids = sorted(set(seed_canon.values()))
        total = len(identity_ids)
        result["capped"] = len(_matching_employee_ids(c, first, last, cred, npi)) > MAX_IDS
        result["total"] = total

        start = (page - 1) * page_size
        page_cids = identity_ids[start : start + page_size]

        member_ids = _members_of_canonical(page_cids, seed_canon)
        assembled = _assemble(c, member_ids)
        member_canon = _canonical_map(c, member_ids)
        by_identity: dict[int, list[dict]] = defaultdict(list)
        for emp in assembled:
            by_identity[member_canon.get(emp["cami_employee_id"], emp["cami_employee_id"])].append(emp)
        result["identities"] = [_consolidate(by_identity.get(cid, []), cid) for cid in page_cids]
        result["suggestions"] = _suggestions(c, first, last, set(seed_ids))

    result["count"] = len(result["identities"])
    result["has_more"] = start + page_size < total
    return result


def overview_stats() -> dict[str, Any]:
    def count(c, table: str) -> int:
        return int(c.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)

    with engine.connect() as c:
        total_employees = count(c, "employees")
        return {
            "total_employees": total_employees,
            "credential_matches": count(c, "credential_matches"),
            "exclusion_matches": count(c, "matches"),
            "resolutions": count(c, "credential_match_resolutions"),
            "exclusion_actions": count(c, "match_actions"),
        }


def _redacted_url() -> str:
    from .db import DATABASE_URL

    url = DATABASE_URL
    if "@" in url:
        scheme, rest = url.split("://", 1)
        _, host = rest.split("@", 1)
        return f"{scheme}://***@{host}"
    return url
```

**Note (front-end impact, flagged not silently absorbed):** the response shape changes in one place — each identity/employee record's `individuals`/`entities` arrays are replaced by a single `employee` dict (flat schema has no per-employee child list), and `addresses` is dropped (the mirror's separate `Address` table doesn't exist in the real schema; address fields live directly on `employees` as `address1`/`city`/`state`/`zip` if the front-end wants them later — out of scope for this plan). `static/index.html`'s `rIdentity()`/tree-rendering functions that reference `ind.names`/`ind.credentials`/`ind.addresses` or `m.individuals`/`m.entities` will need matching updates — this is called out here as a required follow-up but the HTML/JS rewrite itself is left to a subsequent task since it's front-end, not query-layer, work.

- [ ] **Step 3: Manual smoke-test against the real DB (no automated test harness exists for the Explorer)**

Run: `cd C:\new-codes\golden-profile-explorer && ..\golden-profile-service\.venv\Scripts\python.exe -c "
from app.queries import search_profiles, overview_stats
print(overview_stats())
r = search_profiles('<first name>', '<last name>')
print(r['total'], r['count'])
for ident in r['identities']:
    print(ident['identity_id'], ident['display_name'], ident['member_employee_ids'], ident['has_conflict'])
"`
Substitute `<first name>`/`<last name>` for a name pair you've confirmed locally (via a direct DB query, not committed here) has two employee records sharing a strong key (e.g. the same `certification_number`+`certification_state`) — do not hardcode a specific real person's name/id/license number into this doc. Expected: `overview_stats()` prints non-zero counts (do not hardcode exact numbers into an assertion since the DB is live and changes); the search returns one identity consolidating both employee ids via the shared license.

- [ ] **Step 4: Commit**

```bash
cd C:\new-codes\golden-profile-explorer
git status
```

(Note: per prior session notes, this directory is NOT a git repository — edits here are in-place only, no commit step applies. Confirm with `git status` first; if it unexpectedly *is* a repo, commit as `git add app/db.py app/queries.py && git commit -m "Query streamline_local directly with live scoring-based resolution"`.)

---

### Task 9: End-to-end verification against the live local DB

**Files:** none (verification only).

**Interfaces:** none — this task exercises Tasks 1-8 together.

- [ ] **Step 1: Run the full service test suite one more time**

Run: `cd C:\new-codes\golden-profile-service && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, all green.

- [ ] **Step 2: Run the client's Golden Profile PHPUnit suite one more time**

Run: `cd C:\new-codes\client && php vendor/bin/phpunit --no-coverage --filter GoldenProfile`
Expected: PASS.

- [ ] **Step 3: Start the service against the real local streamline_local and hit it live**

Run: `cd C:\new-codes\golden-profile-service && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8137 &`
Then: `curl -s -X POST http://127.0.0.1:8137/api/v1/search/general -H "Content-Type: application/json" -d "{\"params_first_name\":\"<first name>\",\"params_last_name\":\"<last name>\"}"` — use the same locally-confirmed shared-license name pair as Task 8 Step 3 (do not hardcode a specific real person's name/id/license number into this doc).
Expected: `canonical_employee_ids` includes both employee ids; `credential_matches` includes the shared license's registry entries; response has no 500 error.

- [ ] **Step 4: Start the Explorer and confirm the UI still loads (query layer only — front-end fields noted in Task 8 may show blank/undefined for the changed shape)**

Run: `cd C:\new-codes\golden-profile-service && .venv\Scripts\python.exe -m uvicorn app.main:app --app-dir C:\new-codes\golden-profile-explorer --port 8150 &`
Then open `http://localhost:8150` in a browser and search using the same name pair.
Expected: the page loads, `/api/health` and `/api/stats` return 200, the search returns a non-error JSON payload in the Network tab (visual rendering of the identity card is a known follow-up per Task 8's note).

- [ ] **Step 5: Report results, not just "done" — surface any deviations found in Steps 1-4 to the user before considering the plan complete.**

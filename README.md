# Golden Profile Service (CAMI Resource Provider)

A standalone Python (FastAPI + SQLAlchemy) service that:

1. **Ingests** employee, credential-match and exclusion-match data pushed from
   CAMI over HTTP, and stores it in **its own database** as versioned snapshots.
2. **Serves as an alternative source of licensing data** for CAMI: when CAMI runs
   a credentialing check, it asks this service first, which either returns a
   cached valid result, auto-resolves a known name mismatch, or tells CAMI to
   trigger a bot scrape.

This implements the schema and the four processes described in `resourceProvider.pdf`.

## Concepts

### Versioned snapshots (`current` flag)
Every ingest is stored as a new row with `current = 1`; the previous current
row(s) for the same logical key are flipped to `current = 0`. This gives a full
history (Slowly-Changing-Dimension type 2) while a single "golden" record stays
easy to query.

| Table | Logical key that gets superseded |
|-------|----------------------------------|
| `individuals` | `cami_employee_id` |
| `entities` | `cami_employee_id` |
| `credential_matches` | `cami_employee_id` + `credential_database_id` + `params_credential_id` + `params_license_type` |
| `exclusion_matches` | `cami_employee_id` + `exclusion_list_id` |

### The four processes
1. **Syncing Employee Data** — `POST /api/v1/employees/individuals` or `/entities`.
   Individuals and entities are stored on separate tables with their names,
   addresses, and (for individuals) licensing credentials.
2. **Syncing Credential Matches** — `POST /api/v1/credential-matches` (optionally
   with `resolutions`).
3. **Syncing Exclusion Matches** — `POST /api/v1/exclusion-matches` (optionally
   with `actions`).
4. **Credentialing Search** — `POST /api/v1/search/credential`. Returns an
   `action`:
   - `return_result` — a valid, unexpired current match was found.
   - `auto_resolve_name_mismatch` — a match was found that carries a recorded
     name-mismatch resolution; CAMI should return it and auto-resolve.
   - `trigger_scrape` — nothing usable; CAMI should run the bots.

## Quick start

```bash
cd golden-profile-service
py -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

cp .env.example .env        # then edit API_KEYS / DATABASE_URL
uvicorn app.main:app --reload
```

Open the interactive docs at http://127.0.0.1:8000/docs.
Tables are auto-created on startup.

### Database
Defaults to a local SQLite file (`golden_profile.db`) for zero-setup runs. For
production set `DATABASE_URL` to MySQL/MariaDB (the schema types match CAMI):

```
DATABASE_URL=mysql+pymysql://user:password@host:3306/golden_profile
```

### Auth
All `/api/v1/*` endpoints require the `X-API-Key` header, validated against the
comma-separated `API_KEYS` setting. Leaving `API_KEYS` empty disables auth
(local dev only).

```bash
curl -X POST http://127.0.0.1:8000/api/v1/search/credential \
  -H "X-API-Key: dev-cami-key" -H "Content-Type: application/json" \
  -d '{"credential_database_id":1,"params_credential_id":"RN-55555","params_license_type":"RN","params_first_name":"John","params_last_name":"Smith"}'
```

## Reference data
Registries and exclusion lists are the FK targets for matches. Seed them via:
- `POST /api/v1/credential-databases`, `GET /api/v1/credential-databases`
- `POST /api/v1/exclusion-lists`, `GET /api/v1/exclusion-lists`

Or run `python -m scripts.seed` (see `scripts/seed.py`) for a demo dataset.

## Project layout
```
app/
  main.py            FastAPI app + startup table creation
  config.py          env-driven settings
  database.py        engine / session / Base
  models.py          SQLAlchemy models (full schema)
  schemas.py         Pydantic request/response contracts
  security.py        X-API-Key auth
  hashing.py         SSN/TIN hash + last-four helpers
  services/          the four processes (business logic)
  routers/           HTTP endpoints
tests/               end-to-end tests for all four processes
scripts/seed.py      demo reference + sample data
```

## Tests
```bash
./.venv/Scripts/python.exe -m pytest -q
```

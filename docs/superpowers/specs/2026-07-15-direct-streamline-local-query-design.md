# Golden Profile: query streamline_local directly (drop the mirror)

## Context

`golden-profile-service` currently ingests employee / credential-match / exclusion-match
snapshots pushed from the CAMI client into its own `golden_profile` MySQL database, and
answers searches against that mirrored copy. `golden-profile-explorer` reads the same
mirror. This spec replaces the mirror with live queries against `streamline_local` (the
actual CAMI database, same MySQL server as the mirror — `127.0.0.1:33066`, just a
different schema name) — no more sync, no more staleness, no more duplicated data.

## Goals

- Service and Explorer both read `streamline_local` live; no local storage of
  employee/credential/exclusion data anywhere.
- Keep the existing search contract (`/api/v1/search/credential`, `/api/v1/search/general`)
  unchanged so the CAMI client's search-before-scrape integration needs no changes.
- Keep cross-employee canonical merging (the SSN/NPI/license identity graph) — computed
  live per search instead of read from a persisted table.
- Remove all sync/ingestion machinery on both the service and client sides — it no longer
  has a job to do once there's no mirror to keep in sync.

## Non-goals

- No schema changes to `streamline_local` (it's a real, shared database — read-only access
  only from the service/Explorer).
- No attempt to replicate CAMI's live exclusion-matching *algorithm* (name/SSN/NPI hash
  matching against `exclusion_search_table_view`) — we only read *existing* `matches` rows
  that CAMI's own check flow already created, we don't compute new ones.

## Real schema (streamline_local) vs. the old mirror

Discovered by inspecting the live DB directly (`DESCRIBE <table>` via pymysql), not by
assumption:

| Concept | Old mirror table | Real `streamline_local` table | Notes |
|---|---|---|---|
| Employee (individual or entity) | `individuals` / `entities` (split) | `employees` (one flat table) | Entity vs. individual: non-empty `business` column. Names, `ssn_hash`, `npi`, `certification_number`/`certification_state`, `date_of_birth` are direct columns. AKAs are `alt_first_name_1..5`/`alt_last_name_1..5`/`alt_maiden_name_1..2`. |
| Credential match | `credential_matches` (own shape) | `credential_matches` (real shape) | Real table has `employee_id` (not `cami_employee_id`), `current` (bool, filter on this instead of the mirror's `ROW_NUMBER()` latest-per-registry trick), `type` (int status code), `match_summary_status`/`match_summary_status_code`, `credential_id`, `match` (JSON blob), `date_updated`/`last_modified` (no `check_date` column — use these for staleness). No `params_first_name`/`params_last_name` on the row — join `employees`. |
| Credential match resolution note | `credential_match_resolutions` | `credential_match_resolutions` | Same name and shape already — no change needed. |
| Exclusion match | `exclusion_matches` (own shape) | `matches` (`employee_id`, `exclusion_record_id`, `is_npi_match`, `is_ssn_match`, `is_canonical_name_match`, `is_aka_name_match`, `is_diminutive_name_match`, `is_upin_match`, `is_license_number_match`, `is_npi_mismatch`, `metadata` JSON) joined to `exclusion_records` (the matched record blob) and `exclusion_lists` (prefix/description) | Verified live: 12,890 rows in `matches`. |
| Exclusion resolution action | `exclusion_match_actions` | `match_actions` (`match_id`, `action_type`, `note`, `status`, `is_*_mismatch`, `resolved_via`) | Same shape as the mirror's version, different table name. |
| Canonical identity graph | `employee_canonical` table, rebuilt on a schedule | **not persisted** — computed live per search | See below. |

## Resolution (cross-employee canonical merging)

Port `resolution.py`'s strong-key transitive closure to read directly from
`streamline_local.employees` + `streamline_local.credential_matches`:

- `ssn:{employees.ssn_hash}` (already a salted hash column on `employees` — no derivation
  needed, unlike the old mirror which sometimes had it empty because the client only sent
  `ssn_last_four`).
- `npi:{employees.npi}` (also directly on `employees` now, not only inside a JSON blob).
- `lic:{credential_matches.registry}:{credential_matches.credential_id}`.

Closure is computed live, the same way the mirror's hot path already falls back to a live
closure for un-rebuilt seeds (`resolution.group_for_seeds`) — that fallback code path is
close to what we need permanently now; there's just no persisted table to check first and
no `RESOLVE_USE_PERSISTED` flag. `POST /api/v1/resolve/rebuild` and the
`golden-profile:rebuild-graph` scheduled command are removed — nothing to rebuild.
`GET /api/v1/resolve/employee/{id}` stays as an endpoint, same response shape, just computed
on every call.

Name is still never a merge key (unchanged invariant — "two John Millers" stay separate
unless linked by a strong key).

## Removed

**Service (`golden-profile-service`):**
- `app/services/employee_sync.py`, `app/services/credential_sync.py` (ingestion — nothing
  to ingest).
- `app/models.py`'s mirror ORM tables (`Individual`, `Entity`, `IndividualName`,
  `EntityName`, `LicensingCredential`, `Address*`, `CredentialMatch`, `CanonicalEmployee`,
  `CredentialMatchResolution`, `ExclusionMatch`, `ExclusionMatchAction`) — replaced by raw
  `text()` queries against `streamline_local` (same style Explorer already uses; we don't
  own this schema so we don't model it as our own tables).
- Write/ingest endpoints: `POST /api/v1/employees`, `POST /api/v1/credential-matches`
  (+ `/bulk`), `POST /api/v1/exclusion-matches`, `POST /api/v1/resolve/rebuild`.
- The `golden_profile` database itself (config, `DATABASE_URL` now points at
  `streamline_local`).
- API-key auth for ingestion (`X-API-Key`) — no longer needed once there's nothing to push;
  re-evaluate whether the read-only search endpoints need their own auth story (not decided
  here — flag as a follow-up, not a blocker).

**Client (`C:\new-codes\client`):**
- `App\Observers\GoldenProfile\CredentialMatchGoldenProfileObserver` (+ its registration on
  `CredentialMatch` and `CredentialMatchFromCommand` in `EventServiceProvider::boot()`).
- `SyncEmployeeToGoldenProfile`, `SyncExclusionMatchToGoldenProfile` listeners.
- `App\Jobs\GoldenProfile\PushToGoldenProfileJob`.
- `golden-profile:reconcile`, `golden-profile:work` artisan commands + the
  `golden_profile_worker` supervisor program (ansible template + role entry).
- `GoldenProfileGateway`'s sync methods: `syncEmployee`, `syncCredentialMatch`,
  `syncExclusionMatch`, `syncCredentialMatchesBulk`, `buildIndividualPayload`,
  `buildEntityPayload`, `buildCredentialMatchPayload`, `dispatchJob`.
- Feature flags `GOLDEN_PROFILE_SYNC_ENABLED`, `GOLDEN_PROFILE_QUEUE_ENABLED`,
  `GOLDEN_PROFILE_QUEUE_CONNECTION`.

## Kept / rewritten

- `POST /api/v1/search/credential` (`CredentialSearchIn`/`Out`) — same request/response
  contract. Query rewritten: find the employee by name (+ optional npi/credential id),
  pull matching `credential_matches` where `current=1`, apply the existing TTL/staleness
  rule (`_is_stale`) using `date_updated`/`last_modified` in place of `check_date`.
- `POST /api/v1/search/general` (`GeneralSearchIn`/`Out`) — same contract; resolves the
  query name to a canonical group (live closure above), gathers credential + exclusion
  matches across the whole group, keeps conflict flagging (same-registry+license,
  disagreeing validity) and `has_conflict`/`conflicts`.
- `GET /api/v1/resolve/employee/{id}`, `POST /api/v1/resolve/suggestions` (fuzzy
  name-variant review candidates) — same contracts, computed live.
- `GET /api/v1/stats` metrics endpoint — unchanged (in-memory counters).
- Client: `GoldenProfileGateway::lookupCredentialData()` / `generalSearch()` — unchanged
  call sites (`EmployeeController::updateUncachedCredentialMatchesFromCache()` keeps
  calling GP the same way for search-before-scrape). `GOLDEN_PROFILE_SEARCH_ENABLED`,
  `GOLDEN_PROFILE_BASE_URL`/`_API_KEY` flags stay.
- Explorer: identity-centric consolidated view (one card per canonical identity, AKA
  names, credential/exclusion matches, conflict badge, "possible same person" suggestions)
  stays, same UI. `queries.py` rewritten against the real tables above; `DATABASE_URL`
  points at `streamline_local`.

## Data flow (new)

1. CAMI runs a check → writes `employees`/`credential_matches`/`matches` as it always has
   (this part of CAMI is untouched — we removed the *push-to-mirror* side effect, not the
   check flow itself).
2. CAMI's `EmployeeController` search-before-scrape hook calls
   `GoldenProfileGateway::lookupCredentialData()` → service `/api/v1/search/credential` →
   service queries `streamline_local` live → returns `return_result` /
   `auto_resolve_name_mismatch` / `trigger_scrape`, same as before, but the data is *always
   current* (no sync lag, no reconcile job needed to catch missed writes).
3. Explorer search → service-independent, queries `streamline_local` live directly (as it
   does today against the mirror).

## Error handling

- Service loses its own DB entirely — no more "GP DB down" failure mode distinct from
  "`streamline_local` down." Gateway's existing fail-safe behavior (timeout → treat as
  cache-miss → scrape) is unchanged and now covers this case too.
- No dual-write / partial-sync failure modes to handle (they're eliminated along with the
  sync code).

## Testing

- Service: existing pytest suite gets rewritten test doubles — tests currently seed the
  mirror's SQLite tables directly; they'll need to seed `streamline_local`-shaped tables
  instead (still SQLite for tests, same portable-SQL discipline the mirror code followed).
  Search/resolution/conflict/staleness test *behavior* stays the same; only the seed
  fixtures and column names change.
- Client: PHPUnit tests for the removed observer/listeners/job/commands are deleted along
  with the code. Gateway tests for `lookupCredentialData`/`generalSearch` are kept (mocked
  HTTP, unaffected by the service's internal query rewrite).
- Manual verification: repeat the same "alice vawter" / "Pearlie Brown" live-DB checks used
  to verify the mirror (conflict badge, SSN-linked merge, AKA names) but against
  `streamline_local`, confirming identical results now that it's the same underlying data
  with one less hop.

## Open follow-ups (explicitly not solved here)

- Auth story for the now-read-only service (drop API key entirely? keep it as a basic
  access gate even without writes?).
- Whether `streamline_local` access should go through a dedicated read-only MySQL user
  instead of `root` (currently local-dev-only credentials; worth tightening before this
  pattern is considered for a shared/prod-like environment).

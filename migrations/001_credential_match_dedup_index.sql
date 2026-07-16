-- Manual migration 001 — credential-match dedup index (MySQL/MariaDB).
--
-- This service has no Alembic: Base.metadata.create_all() only creates MISSING
-- tables, it never adds indexes to an existing table. Fresh deploys get the
-- index from the model (Index "ix_cred_match_dedup"); an already-running prod
-- DB needs this applied by hand.
--
-- Why: the idempotency dedup lookup runs
--   WHERE cami_credential_match_id = ? AND check_date = ?
-- Without a composite index that scans every row for the given match id.

ALTER TABLE credential_matches
    ADD INDEX ix_cred_match_dedup (cami_credential_match_id, check_date);

-- The old single-column index (created when the column was index=True) is now
-- redundant — the composite's leftmost prefix covers it. Confirm its name with
-- SHOW INDEX FROM credential_matches; then drop it:
-- ALTER TABLE credential_matches
--     DROP INDEX ix_credential_matches_cami_credential_match_id;

-- Optional hardening: enforce idempotency at the DB level under concurrency.
-- MySQL allows multiple NULLs in a UNIQUE index, which matches the app's
-- "append when either key is null" fallback. Only apply after de-duping any
-- existing rows, or the ALTER fails.
-- ALTER TABLE credential_matches
--     ADD UNIQUE INDEX uq_cred_match_event (cami_credential_match_id, check_date);

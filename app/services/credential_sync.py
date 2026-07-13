"""Process: Syncing Credential Matches Data.

When a credential match is saved with a result in CAMI, insert a fresh snapshot.
Snapshots are append-only — the search picks the freshest one by check_date, so
there is no "current" flag to maintain or older rows to supersede.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import metrics, models, schemas


def _sync_one(
    db: Session, payload: schemas.CredentialMatchSyncIn
) -> schemas.CredentialMatchSyncResult:
    """Insert one snapshot. Does NOT commit — the caller owns the transaction so
    a batch can commit atomically."""
    registry = (payload.registry or "").strip().lower()

    cm = models.CredentialMatch(
        cami_employee_id=payload.cami_employee_id,
        cami_credential_match_id=payload.cami_credential_match_id,
        params_first_name=payload.params_first_name,
        params_middle_name=payload.params_middle_name,
        params_last_name=payload.params_last_name,
        params_credential_id=payload.params_credential_id,
        params_license_type=payload.params_license_type,
        registry=registry,
        match_summary_status=payload.match_summary_status,
        match_context=payload.match_context,
        match=payload.match,
        status=payload.status,
        expiry_date=payload.expiry_date,
        check_date=payload.check_date,
    )
    cm.resolutions = [
        models.CredentialMatchResolution(note=r.note) for r in payload.resolutions
    ]
    db.add(cm)
    db.flush()  # populate cm.id without ending the transaction
    return schemas.CredentialMatchSyncResult(
        id=cm.id,
        cami_employee_id=payload.cami_employee_id,
        registry=registry,
    )


def sync_credential_match(
    db: Session, payload: schemas.CredentialMatchSyncIn
) -> schemas.CredentialMatchSyncResult:
    result = _sync_one(db, payload)
    db.commit()
    metrics.incr(metrics.SYNC_CREDENTIAL_OK)
    return result


def sync_credential_matches_bulk(
    db: Session, payload: schemas.CredentialMatchBulkSyncIn
) -> schemas.CredentialMatchBulkSyncResult:
    """Sync many matches in a single transaction (one commit for the batch)."""
    results = [_sync_one(db, item) for item in payload.items]
    db.commit()
    metrics.incr(metrics.SYNC_CREDENTIAL_OK, len(results))
    metrics.incr(metrics.SYNC_CREDENTIAL_BULK_OK)
    return schemas.CredentialMatchBulkSyncResult(count=len(results), results=results)

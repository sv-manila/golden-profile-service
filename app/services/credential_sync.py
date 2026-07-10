"""Process: Syncing Credential Matches Data.

When a credential match is saved with a result in CAMI, insert a fresh snapshot
with current=1 and flip preexisting snapshots for the same logical credential
(employee + registry + credential id + license type) to current=0.
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import models, schemas
from .reference_resolver import resolve_credential_database_id


def sync_credential_match(
    db: Session, payload: schemas.CredentialMatchSyncIn
) -> schemas.CredentialMatchSyncResult:
    credential_database_id = resolve_credential_database_id(
        db, id=payload.credential_database_id, prefix=payload.registry_prefix
    )

    # The logical key for "the same credential" is employee + registry + the
    # identifying params. Flip any current snapshot for that key to current=0.
    superseded = list(
        db.scalars(
            select(models.CredentialMatch.id).where(
                models.CredentialMatch.cami_employee_id == payload.cami_employee_id,
                models.CredentialMatch.credential_database_id == credential_database_id,
                models.CredentialMatch.params_credential_id == payload.params_credential_id,
                models.CredentialMatch.params_license_type == payload.params_license_type,
                models.CredentialMatch.current.is_(True),
            )
        )
    )
    if superseded:
        db.execute(
            update(models.CredentialMatch)
            .where(models.CredentialMatch.id.in_(superseded))
            .values(current=False)
        )

    cm = models.CredentialMatch(
        cami_employee_id=payload.cami_employee_id,
        cami_credential_match_id=payload.cami_credential_match_id,
        params_first_name=payload.params_first_name,
        params_middle_name=payload.params_middle_name,
        params_last_name=payload.params_last_name,
        params_credential_id=payload.params_credential_id,
        params_license_type=payload.params_license_type,
        credential_database_id=credential_database_id,
        current=True,
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
    db.commit()
    return schemas.CredentialMatchSyncResult(
        id=cm.id,
        cami_employee_id=payload.cami_employee_id,
        credential_database_id=credential_database_id,
        superseded_ids=superseded,
    )

"""Process: Syncing Exclusion Matches Data.

When an exclusion match is saved in CAMI, insert a fresh snapshot with
current=1 and flip preexisting snapshots for the same logical match
(employee + exclusion list) to current=0.
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import models, schemas
from .reference_resolver import resolve_exclusion_list_id


def _decode_hash(value: str | None) -> bytes | None:
    if not value:
        return None
    try:
        return bytes.fromhex(value)
    except ValueError:
        return value.encode()[:16]


def sync_exclusion_match(
    db: Session, payload: schemas.ExclusionMatchSyncIn
) -> schemas.ExclusionMatchSyncResult:
    exclusion_list_id = resolve_exclusion_list_id(
        db, id=payload.exclusion_list_id, prefix=payload.exclusion_list_prefix
    )

    superseded = list(
        db.scalars(
            select(models.ExclusionMatch.id).where(
                models.ExclusionMatch.cami_employee_id == payload.cami_employee_id,
                models.ExclusionMatch.exclusion_list_id == exclusion_list_id,
                models.ExclusionMatch.current.is_(True),
            )
        )
    )
    if superseded:
        db.execute(
            update(models.ExclusionMatch)
            .where(models.ExclusionMatch.id.in_(superseded))
            .values(current=False)
        )

    em = models.ExclusionMatch(
        cami_employee_id=payload.cami_employee_id,
        cami_match_id=payload.cami_match_id,
        params_first_name=payload.params_first_name,
        params_middle_name=payload.params_middle_name,
        params_last_name=payload.params_last_name,
        exclusion_list_id=exclusion_list_id,
        current=True,
        match=payload.match,
        hash=_decode_hash(payload.hash),
        is_npi_match=payload.is_npi_match,
        is_canonical_name_match=payload.is_canonical_name_match,
        is_diminutive_name_match=payload.is_diminutive_name_match,
        is_aka_name_match=payload.is_aka_name_match,
        is_npi_mismatch=payload.is_npi_mismatch,
        is_upin_match=payload.is_upin_match,
        is_ssn_match=payload.is_ssn_match,
        is_license_number_match=payload.is_license_number_match,
        date_contacted_agency=payload.date_contacted_agency,
        check_date=payload.check_date,
    )
    em.actions = [
        models.ExclusionMatchAction(
            action_type=a.action_type,
            note=a.note,
            resolution_source_data=a.resolution_source_data,
            status=a.status,
            is_dob_mismatch=a.is_dob_mismatch,
            is_ssn_mismatch=a.is_ssn_mismatch,
            is_first_name_mismatch=a.is_first_name_mismatch,
            is_middle_name_mismatch=a.is_middle_name_mismatch,
            is_last_name_mismatch=a.is_last_name_mismatch,
            is_address_mismatch=a.is_address_mismatch,
            is_npi_mismatch=a.is_npi_mismatch,
            is_job_mismatch=a.is_job_mismatch,
            resolved_via=a.resolved_via,
        )
        for a in payload.actions
    ]
    db.add(em)
    db.commit()
    return schemas.ExclusionMatchSyncResult(
        id=em.id,
        cami_employee_id=payload.cami_employee_id,
        exclusion_list_id=exclusion_list_id,
        superseded_ids=superseded,
    )

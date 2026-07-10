"""Process: Syncing Employee Data.

When an employee is created/updated in CAMI, insert a fresh snapshot with
current=1 and flip all preexisting snapshots for that cami_employee_id to
current=0. Individuals and entities are handled on separate tables.
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import models, schemas
from ..hashing import derive_hash, last_four


def sync_individual(db: Session, payload: schemas.IndividualSyncIn) -> schemas.EmployeeSyncResult:
    # 1. Flip preexisting current snapshots for this employee to current=0.
    superseded = list(
        db.scalars(
            select(models.Individual.id).where(
                models.Individual.cami_employee_id == payload.cami_employee_id,
                models.Individual.current.is_(True),
            )
        )
    )
    if superseded:
        db.execute(
            update(models.Individual)
            .where(models.Individual.id.in_(superseded))
            .values(current=False)
        )

    # 2. Insert the new current snapshot.
    ssn_hash = payload.ssn_hash or derive_hash(payload.social_security_num)
    ssn_l4 = payload.ssn_last_four or last_four(payload.social_security_num)

    ind = models.Individual(
        npi=payload.npi,
        cami_employee_id=payload.cami_employee_id,
        current=True,
        facility_id=payload.facility_id,
        terminated=payload.terminated,
        date_of_termination=payload.date_of_termination,
        date_termination_entered=payload.date_termination_entered,
        termination_note=payload.termination_note,
        date_of_birth=payload.date_of_birth,
        date_hire=payload.date_hire,
        job_title=payload.job_title,
        social_security_num=payload.social_security_num,
        ssn_hash=ssn_hash,
        ssn_last_four=ssn_l4,
        mmis_number=payload.mmis_number,
        record_status=payload.record_status,
        last_updated_in_cami=payload.last_updated_in_cami,
    )
    ind.names = [
        models.IndividualName(
            first_name=n.first_name,
            middle_name=n.middle_name,
            last_name=n.last_name,
            maiden_name=n.maiden_name,
        )
        for n in payload.names
    ]
    ind.credentials = [
        models.LicensingCredential(
            certification_number=c.certification_number,
            certification_state=c.certification_state,
            license_type_id=c.license_type_id,
            license_type=c.license_type,
            csl_number=c.csl_number,
            csl_state=c.csl_state,
            dea_number=c.dea_number,
            certification_board=c.certification_board,
        )
        for c in payload.credentials
    ]
    db.add(ind)
    db.flush()

    for addr in payload.addresses:
        a = models.Address(**addr.model_dump())
        db.add(a)
        db.flush()
        db.add(models.IndividualAddress(address_id=a.id, individual_id=ind.id))

    db.commit()
    return schemas.EmployeeSyncResult(
        employee_type="individual",
        cami_employee_id=payload.cami_employee_id,
        id=ind.id,
        superseded_ids=superseded,
    )


def sync_entity(db: Session, payload: schemas.EntitySyncIn) -> schemas.EmployeeSyncResult:
    superseded = list(
        db.scalars(
            select(models.Entity.id).where(
                models.Entity.cami_employee_id == payload.cami_employee_id,
                models.Entity.current.is_(True),
            )
        )
    )
    if superseded:
        db.execute(
            update(models.Entity)
            .where(models.Entity.id.in_(superseded))
            .values(current=False)
        )

    tin_hash = payload.tin_hash or derive_hash(payload.tin)
    tin_l4 = payload.tin_last_four or last_four(payload.tin)

    ent = models.Entity(
        npi=payload.npi,
        cami_employee_id=payload.cami_employee_id,
        current=True,
        facility_id=payload.facility_id,
        terminated=payload.terminated,
        date_of_termination=payload.date_of_termination,
        date_termination_entered=payload.date_termination_entered,
        termination_note=payload.termination_note,
        upin=payload.upin,
        tin=payload.tin,
        tin_hash=tin_hash,
        tin_last_four=tin_l4,
        mmis_number=payload.mmis_number,
        last_updated_in_cami=payload.last_updated_in_cami,
    )
    ent.names = [models.EntityName(name=n.name) for n in payload.names]
    db.add(ent)
    db.flush()

    for addr in payload.addresses:
        a = models.Address(**addr.model_dump())
        db.add(a)
        db.flush()
        db.add(models.EntityAddress(address_id=a.id, entity_id=ent.id))

    db.commit()
    return schemas.EmployeeSyncResult(
        employee_type="entity",
        cami_employee_id=payload.cami_employee_id,
        id=ent.id,
        superseded_ids=superseded,
    )

"""Reference-data endpoints: credential databases (registries) & exclusion lists.

These back the FK targets used by matches. CAMI (or an admin) seeds them so the
Golden Profile knows which registry / exclusion list each match belongs to.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import require_api_key

router = APIRouter(prefix="/api/v1", tags=["reference"], dependencies=[Depends(require_api_key)])


@router.post("/credential-databases", response_model=schemas.CredentialDatabaseOut, status_code=201)
def create_credential_database(payload: schemas.CredentialDatabaseIn, db: Session = Depends(get_db)):
    row = models.CredentialDatabase(**payload.model_dump())
    db.add(row)
    db.commit()
    return row


@router.get("/credential-databases", response_model=list[schemas.CredentialDatabaseOut])
def list_credential_databases(db: Session = Depends(get_db)):
    return list(db.scalars(select(models.CredentialDatabase)))


@router.post("/exclusion-lists", response_model=schemas.ExclusionListOut, status_code=201)
def create_exclusion_list(payload: schemas.ExclusionListIn, db: Session = Depends(get_db)):
    row = models.ExclusionList(**payload.model_dump())
    db.add(row)
    db.commit()
    return row


@router.get("/exclusion-lists", response_model=list[schemas.ExclusionListOut])
def list_exclusion_lists(db: Session = Depends(get_db)):
    return list(db.scalars(select(models.ExclusionList)))

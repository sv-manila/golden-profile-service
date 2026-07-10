"""Credentialing search endpoint — the alternative licensing source for CAMI."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..security import require_api_key
from ..services import search as search_service

router = APIRouter(prefix="/api/v1/search", tags=["search"], dependencies=[Depends(require_api_key)])


@router.post("/credential", response_model=schemas.CredentialSearchResult)
def search_credential(payload: schemas.CredentialSearchIn, db: Session = Depends(get_db)):
    """Answer a CAMI credentialing check from the Golden Profile.

    Returns one of three actions: `return_result` (valid cached match),
    `auto_resolve_name_mismatch` (match + recorded resolution), or
    `trigger_scrape` (nothing usable — CAMI should run the bots).
    """
    return search_service.search_credential(db, payload)


@router.post("/general", response_model=schemas.GeneralSearchResult)
def general_search(payload: schemas.GeneralSearchIn, db: Session = Depends(get_db)):
    """Name-based general search.

    Given a required first + last name, returns the latest current credential
    match per registry for that name, plus current exclusion matches for that
    name. Optional `params_credential_id` (license number) and
    `params_certification_state` filter the credential matches when provided.
    """
    return search_service.general_search(db, payload)

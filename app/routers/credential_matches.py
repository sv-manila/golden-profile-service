"""Credential-match sync endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..security import require_api_key
from ..services import credential_sync

router = APIRouter(
    prefix="/api/v1/credential-matches",
    tags=["credential-matches"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=schemas.CredentialMatchSyncResult, status_code=201)
def sync_credential_match(payload: schemas.CredentialMatchSyncIn, db: Session = Depends(get_db)):
    """Sync a credential match (with any resolutions) from CAMI."""
    return credential_sync.sync_credential_match(db, payload)


@router.post("/bulk", response_model=schemas.CredentialMatchBulkSyncResult, status_code=201)
def sync_credential_matches_bulk(
    payload: schemas.CredentialMatchBulkSyncIn, db: Session = Depends(get_db)
):
    """Batch-sync many credential matches in one request (one DB transaction).

    Used by the client's queued reconciler/Check-List batch so a list of N
    employees costs one round-trip instead of N."""
    return credential_sync.sync_credential_matches_bulk(db, payload)

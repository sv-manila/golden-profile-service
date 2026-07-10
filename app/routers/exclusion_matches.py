"""Exclusion-match sync endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..security import require_api_key
from ..services import exclusion_sync

router = APIRouter(
    prefix="/api/v1/exclusion-matches",
    tags=["exclusion-matches"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=schemas.ExclusionMatchSyncResult, status_code=201)
def sync_exclusion_match(payload: schemas.ExclusionMatchSyncIn, db: Session = Depends(get_db)):
    """Sync an exclusion match (with any actions) from CAMI."""
    return exclusion_sync.sync_exclusion_match(db, payload)

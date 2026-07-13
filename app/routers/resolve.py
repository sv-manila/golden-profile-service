"""Entity-resolution endpoint — unify records for one real person."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..security import require_api_key
from ..services import resolution as resolution_service

router = APIRouter(prefix="/api/v1/resolve", tags=["resolve"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=schemas.ResolveOut)
def resolve(payload: schemas.ResolveIn, db: Session = Depends(get_db)):
    """Resolve identifiers/name to a canonical person.

    A strong identifier (NPI, or registry + license number) merges every
    cami_employee_id that shares it, transitively. A name-only lookup returns
    candidates for review — it never merges, because two different people can
    share a name.
    """
    return resolution_service.resolve(db, payload)

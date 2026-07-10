"""Employee sync endpoints (individuals & entities)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..security import require_api_key
from ..services import employee_sync

router = APIRouter(prefix="/api/v1/employees", tags=["employees"], dependencies=[Depends(require_api_key)])


@router.post("/individuals", response_model=schemas.EmployeeSyncResult, status_code=201)
def sync_individual(payload: schemas.IndividualSyncIn, db: Session = Depends(get_db)):
    """Sync an individual employee snapshot from CAMI."""
    return employee_sync.sync_individual(db, payload)


@router.post("/entities", response_model=schemas.EmployeeSyncResult, status_code=201)
def sync_entity(payload: schemas.EntitySyncIn, db: Session = Depends(get_db)):
    """Sync an entity employee snapshot from CAMI."""
    return employee_sync.sync_entity(db, payload)

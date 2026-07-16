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


@router.post("/rebuild", response_model=schemas.ResolveRebuildResult)
def rebuild(db: Session = Depends(get_db)):
    """Rebuild the materialized canonical graph. Run on a schedule behind live
    syncs — the per-employee lookup reads its output instead of rescanning."""
    return resolution_service.rebuild(db)


@router.post("/suggestions", response_model=schemas.ResolveSuggestionsOut)
def suggestions(payload: schemas.ResolveSuggestionsIn, db: Session = Depends(get_db)):
    """Review-only name-variant candidates: same-last-name employees with a
    similar first name who are NOT already strong-id linked. Never merges —
    surfaces possible same-person records for a human to confirm."""
    return schemas.ResolveSuggestionsOut(
        params_first_name=payload.params_first_name,
        params_last_name=payload.params_last_name,
        suggestions=resolution_service.suggestions(
            db, payload.params_first_name, payload.params_last_name
        ),
    )


@router.get("/employee/{cami_employee_id}", response_model=schemas.ResolveOut)
def resolve_employee(cami_employee_id: int, db: Session = Depends(get_db)):
    """Fast canonical-group lookup for one employee, from the materialized graph
    (call /resolve/rebuild first). Returns the unified person's members."""
    return resolution_service.resolve_employee(db, cami_employee_id)

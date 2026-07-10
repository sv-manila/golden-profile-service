"""Process: Credentialing Search Changes.

When CAMI performs a check for a registry, it asks the Golden Profile first.
Flow (from the spec flowchart):

  1. Look for a VALID current credential_match matching the params.
        -> found  => return_result
  2. Otherwise look for a credential_match matching the params that carries a
     name-mismatch resolution (credential_match_resolutions).
        -> found  => auto_resolve_name_mismatch (return result + resolution)
        -> none   => trigger_scrape
  3. Nothing matches at all => trigger_scrape
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import get_settings
from .reference_resolver import resolve_credential_database_id


def _base_params_filter(
    stmt, payload: schemas.CredentialSearchIn, credential_database_id: int, *, include_name: bool
):
    """Add the registry + credential identifier filters (and optionally name)."""
    stmt = stmt.where(
        models.CredentialMatch.credential_database_id == credential_database_id,
        models.CredentialMatch.current.is_(True),
    )
    if payload.params_credential_id:
        stmt = stmt.where(
            models.CredentialMatch.params_credential_id == payload.params_credential_id
        )
    if payload.params_license_type:
        stmt = stmt.where(
            models.CredentialMatch.params_license_type == payload.params_license_type
        )
    if include_name:
        if payload.params_last_name:
            stmt = stmt.where(
                func.lower(models.CredentialMatch.params_last_name)
                == payload.params_last_name.lower()
            )
        if payload.params_first_name:
            stmt = stmt.where(
                func.lower(models.CredentialMatch.params_first_name)
                == payload.params_first_name.lower()
            )
    return stmt


def _is_valid(cm: models.CredentialMatch) -> bool:
    valid_statuses = get_settings().valid_status_set
    status_ok = (cm.match_summary_status or "").upper() in valid_statuses or (
        cm.status or ""
    ).upper() in valid_statuses
    if not status_ok:
        return False
    if cm.expiry_date is not None and cm.expiry_date < date.today():
        return False
    return True


def search_credential(db: Session, payload: schemas.CredentialSearchIn) -> schemas.CredentialSearchResult:
    # Resolve the registry (do not create it for a read-only search).
    credential_database_id = resolve_credential_database_id(
        db, id=payload.credential_database_id, prefix=payload.registry_prefix, create=False
    )
    if credential_database_id is None:
        return schemas.CredentialSearchResult(
            found=False,
            action="trigger_scrape",
            reason="Registry not known to Golden Profile; trigger bot scrape.",
        )

    # Step 1: valid current match on the full params (name included).
    # NULLs-last ordering expressed portably (MySQL has no NULLS LAST):
    # `check_date IS NULL` sorts False(0) before True(1), so non-null dates win.
    stmt = _base_params_filter(
        select(models.CredentialMatch), payload, credential_database_id, include_name=True
    ).order_by(
        models.CredentialMatch.check_date.is_(None),
        models.CredentialMatch.check_date.desc(),
        models.CredentialMatch.id.desc(),
    )
    for cm in db.scalars(stmt):
        if _is_valid(cm):
            return schemas.CredentialSearchResult(
                found=True,
                action="return_result",
                reason="Valid current credential match found in Golden Profile.",
                credential_match=schemas.CredentialMatchOut.model_validate(cm),
            )

    # Step 2: a match on credential params (ignoring name) that has a resolution
    # on record => a previously-resolved name mismatch we can auto-apply.
    stmt = _base_params_filter(
        select(models.CredentialMatch), payload, credential_database_id, include_name=False
    ).order_by(models.CredentialMatch.id.desc())
    for cm in db.scalars(stmt):
        resolution = db.scalars(
            select(models.CredentialMatchResolution)
            .where(models.CredentialMatchResolution.credential_match_id == cm.id)
            .order_by(models.CredentialMatchResolution.id.desc())
        ).first()
        if resolution is not None:
            return schemas.CredentialSearchResult(
                found=True,
                action="auto_resolve_name_mismatch",
                reason="Credential match found with a recorded name-mismatch resolution; auto-resolving.",
                credential_match=schemas.CredentialMatchOut.model_validate(cm),
                resolution=schemas.ResolutionOut.model_validate(resolution),
            )

    # Step 3: nothing usable in the Golden Profile -> tell CAMI to scrape.
    return schemas.CredentialSearchResult(
        found=False,
        action="trigger_scrape",
        reason="No valid match or resolution in Golden Profile; trigger bot scrape.",
    )

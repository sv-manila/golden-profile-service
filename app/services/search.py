"""Process: Credentialing Search Changes.

When CAMI performs a check for a registry, it asks the Golden Profile first.
Flow (from the spec flowchart):

  1. Look for a VALID credential_match matching the params (freshest first).
        -> found  => return_result
  2. Otherwise look for a credential_match matching the params that carries a
     name-mismatch resolution (credential_match_resolutions).
        -> found  => auto_resolve_name_mismatch (return result + resolution)
        -> none   => trigger_scrape
  3. Nothing matches at all => trigger_scrape
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import metrics, models, schemas
from ..config import get_settings


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _match_age_days(cm: models.CredentialMatch) -> int | None:
    """Age of a cached match in days, from check_date (preferred) or date_created.

    None when neither timestamp is available (age unknown)."""
    stamp = cm.check_date or cm.date_created
    if stamp is None:
        return None
    # Stored naive-UTC (see models._now); compare against naive-UTC now.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = now - stamp
    return max(delta.days, 0)


def _is_stale(cm: models.CredentialMatch, ttl_days: int) -> bool:
    """True when a TTL is configured and the match is older than it."""
    if ttl_days <= 0:
        return False
    age = _match_age_days(cm)
    return age is not None and age > ttl_days


def _npi_ok(cm: models.CredentialMatch, npi: str | None) -> bool:
    """True when no NPI filter is set, or the result JSON's `npi` equals it.

    Portable across MySQL/SQLite — parses the stored JSON in Python rather than
    relying on dialect-specific JSON SQL functions."""
    want = _digits(npi)
    if not want:
        return True
    try:
        data = json.loads(cm.match) if cm.match else {}
    except (ValueError, TypeError):
        return False
    return isinstance(data, dict) and _digits(str(data.get("npi") or "")) == want


def _base_params_filter(
    stmt, payload: schemas.CredentialSearchIn, registry: str, *, include_name: bool
):
    """Add the registry + credential identifier filters (and optionally name)."""
    stmt = stmt.where(
        func.lower(models.CredentialMatch.registry) == registry,
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
    # Registry is now a denormalized string on the match itself.
    registry = (payload.registry or "").strip().lower()

    # Effective cache TTL for this registry (0 => disabled, serve any age).
    ttl_days = get_settings().ttl_for_prefix(registry)

    # Step 1: valid match on the full params (name included), freshest first.
    # NULLs-last ordering expressed portably (MySQL has no NULLS LAST):
    # `check_date IS NULL` sorts False(0) before True(1), so non-null dates win.
    stmt = _base_params_filter(
        select(models.CredentialMatch), payload, registry, include_name=True
    ).order_by(
        models.CredentialMatch.check_date.is_(None),
        models.CredentialMatch.check_date.desc(),
        models.CredentialMatch.id.desc(),
    )
    for cm in db.scalars(stmt):
        if _is_valid(cm) and _npi_ok(cm, payload.npi):
            # The rows are newest-first, so this is the freshest valid match.
            # If it is past the registry's TTL, every older one is too — stop
            # and make CAMI re-scrape rather than serve stale compliance data.
            if _is_stale(cm, ttl_days):
                metrics.incr(metrics.SEARCH_STALE)
                metrics.incr(metrics.SEARCH_MISS)
                return schemas.CredentialSearchResult(
                    found=False,
                    action="trigger_scrape",
                    reason=(
                        f"Cached match is stale (age {_match_age_days(cm)}d > "
                        f"TTL {ttl_days}d); trigger bot scrape."
                    ),
                    age_days=_match_age_days(cm),
                )
            age = _match_age_days(cm)
            metrics.incr(metrics.SEARCH_HIT)
            metrics.record_hit_age(age)
            return schemas.CredentialSearchResult(
                found=True,
                action="return_result",
                reason="Valid credential match found in Golden Profile.",
                credential_match=schemas.CredentialMatchOut.model_validate(cm),
                age_days=age,
            )

    # Step 2: a match on credential params (ignoring name) that has a resolution
    # on record => a previously-resolved name mismatch we can auto-apply.
    stmt = _base_params_filter(
        select(models.CredentialMatch), payload, registry, include_name=False
    ).order_by(models.CredentialMatch.id.desc())
    for cm in db.scalars(stmt):
        if not _npi_ok(cm, payload.npi):
            continue
        # Honour the same freshness rule on the resolution path.
        if _is_stale(cm, ttl_days):
            continue
        resolution = db.scalars(
            select(models.CredentialMatchResolution)
            .where(models.CredentialMatchResolution.credential_match_id == cm.id)
            .order_by(models.CredentialMatchResolution.id.desc())
        ).first()
        if resolution is not None:
            age = _match_age_days(cm)
            metrics.incr(metrics.SEARCH_HIT)
            metrics.incr(metrics.SEARCH_RESOLVE)
            metrics.record_hit_age(age)
            return schemas.CredentialSearchResult(
                found=True,
                action="auto_resolve_name_mismatch",
                reason="Credential match found with a recorded name-mismatch resolution; auto-resolving.",
                credential_match=schemas.CredentialMatchOut.model_validate(cm),
                resolution=schemas.ResolutionOut.model_validate(resolution),
                age_days=age,
            )

    # Step 3: nothing usable in the Golden Profile -> tell CAMI to scrape.
    metrics.incr(metrics.SEARCH_MISS)
    return schemas.CredentialSearchResult(
        found=False,
        action="trigger_scrape",
        reason="No valid match or resolution in Golden Profile; trigger bot scrape.",
    )


def general_search(db: Session, payload: schemas.GeneralSearchIn) -> schemas.GeneralSearchResult:
    """Name-based lookup: the latest credential match per registry for a
    first/last name, plus the latest exclusion matches for that name.

    Optional filter (applied to credential matches only): license number
    (`params_credential_id`).
    """
    first = payload.params_first_name.strip().lower()
    last = payload.params_last_name.strip().lower()

    # --- Credential matches: matching name, newest first ---
    cm_stmt = select(models.CredentialMatch).where(
        func.lower(models.CredentialMatch.params_first_name) == first,
        func.lower(models.CredentialMatch.params_last_name) == last,
    )
    if payload.params_credential_id:
        cm_stmt = cm_stmt.where(
            models.CredentialMatch.params_credential_id == payload.params_credential_id
        )
    if not payload.include_expired:
        # Hide expired results by default (an unset expiry_date is not expired).
        cm_stmt = cm_stmt.where(
            or_(
                models.CredentialMatch.expiry_date.is_(None),
                models.CredentialMatch.expiry_date >= date.today(),
            )
        )
    if payload.exclude_no_matches:
        # "No match" results are stored with status = CredentialMatch::NO_MATCH ("2").
        cm_stmt = cm_stmt.where(models.CredentialMatch.status != "2")
    cm_stmt = cm_stmt.order_by(
        models.CredentialMatch.check_date.is_(None),
        models.CredentialMatch.check_date.desc(),
        models.CredentialMatch.id.desc(),
    )

    # Walk the name-matched rows (newest-first) once. Keep the latest match per
    # registry as the "winner", and bucket every row by (registry, license) so
    # we can spot snapshots that disagree with the winner's determination.
    latest_by_registry: dict[str | None, models.CredentialMatch] = {}
    by_registry_license: dict[tuple[str | None, str | None], list[models.CredentialMatch]] = {}
    for cm in db.scalars(cm_stmt):
        if not _npi_ok(cm, payload.npi):
            continue
        latest_by_registry.setdefault(cm.registry, cm)
        by_registry_license.setdefault((cm.registry, cm.params_credential_id), []).append(cm)

    credential_matches = []
    for cm in latest_by_registry.values():
        winner_valid = _is_valid(cm)
        # A conflict is a recent snapshot for the SAME registry + license whose
        # validity determination differs from the winner. Different registries
        # legitimately differ (different scope) — those are not conflicts.
        conflicts = []
        for other in by_registry_license.get((cm.registry, cm.params_credential_id), []):
            if other.id == cm.id:
                continue
            if _is_valid(other) != winner_valid:
                conflicts.append(
                    schemas.GeneralCredentialConflictOut(
                        id=other.id,
                        valid=_is_valid(other),
                        match_summary_status=other.match_summary_status,
                        status=other.status,
                        expiry_date=other.expiry_date,
                        check_date=other.check_date,
                    )
                )
        credential_matches.append(
            schemas.GeneralCredentialMatchOut(
                id=cm.id,
                cami_employee_id=cm.cami_employee_id,
                registry=cm.registry,
                params_first_name=cm.params_first_name,
                params_middle_name=cm.params_middle_name,
                params_last_name=cm.params_last_name,
                params_credential_id=cm.params_credential_id,
                params_license_type=cm.params_license_type,
                match_summary_status=cm.match_summary_status,
                status=cm.status,
                expiry_date=cm.expiry_date,
                check_date=cm.check_date,
                match=cm.match,
                has_conflict=bool(conflicts),
                conflicts=conflicts,
            )
        )

    # --- Exclusion matches: matching name, newest first ---
    ex_stmt = (
        select(models.ExclusionMatch)
        .where(
            func.lower(models.ExclusionMatch.params_first_name) == first,
            func.lower(models.ExclusionMatch.params_last_name) == last,
        )
        .order_by(models.ExclusionMatch.id.desc())
    )
    # Keep only the latest snapshot per (employee, exclusion list) — rows are
    # newest-first, so the first one seen for a key wins.
    exclusion_matches = []
    seen_exclusion_keys: set[tuple[int, str | None]] = set()
    for em in db.scalars(ex_stmt):
        key = (em.cami_employee_id, em.prefix)
        if key in seen_exclusion_keys:
            continue
        seen_exclusion_keys.add(key)
        exclusion_matches.append(
            schemas.GeneralExclusionMatchOut(
                id=em.id,
                cami_employee_id=em.cami_employee_id,
                cami_match_id=em.cami_match_id,
                prefix=em.prefix,
                params_first_name=em.params_first_name,
                params_middle_name=em.params_middle_name,
                params_last_name=em.params_last_name,
                match=em.match,
                is_npi_match=em.is_npi_match,
                is_ssn_match=em.is_ssn_match,
                is_license_number_match=em.is_license_number_match,
                check_date=em.check_date,
            )
        )

    return schemas.GeneralSearchResult(
        params_first_name=payload.params_first_name,
        params_last_name=payload.params_last_name,
        params_credential_id=payload.params_credential_id,
        include_expired=payload.include_expired,
        exclude_no_matches=payload.exclude_no_matches,
        credential_matches=credential_matches,
        exclusion_matches=exclusion_matches,
    )

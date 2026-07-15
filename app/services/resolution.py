"""Entity resolution: unify records that refer to the same real person.

The canonical identity is derived, not assumed. Two cami_employee_ids belong to
the same person when they share a STRONG identifier:

  * NPI                          -> key ``npi:{digits}``
  * registry + license number    -> key ``lic:{registry}:{number}``

Membership is the transitive closure over shared keys (A~B by NPI, B~C by
license => A,B,C are one person). Name is deliberately NOT a merge key: two
different people share a name, and mis-merging a sanction onto the wrong person
is the worst mistake this system can make (the artifact's "two John Millers").
Name-only lookups return candidates for review, never a merge.

Portable across MySQL/SQLite — identifiers are parsed in Python, no dialect JSON.
"""
from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas


def _digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _npi_from_match(raw: str | None) -> str | None:
    try:
        data = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return None
    if isinstance(data, dict):
        npi = _digits(data.get("npi"))
        return npi or None
    return None


def _license_key(registry: str | None, number: str | None) -> str | None:
    reg = (registry or "").strip().lower()
    num = (number or "").strip()
    if reg and num:
        return f"lic:{reg}:{num}"
    return None


def _employee_keys(db: Session) -> dict[int, set[str]]:
    """Map every cami_employee_id to its set of strong-identifier keys."""
    emp_keys: dict[int, set[str]] = defaultdict(set)

    for cm in db.scalars(select(models.CredentialMatch)):
        emp = cm.cami_employee_id
        lic = _license_key(cm.registry, cm.params_credential_id)
        if lic:
            emp_keys[emp].add(lic)
        npi = _npi_from_match(cm.match)
        if npi:
            emp_keys[emp].add(f"npi:{npi}")

    for ind in db.scalars(select(models.Individual).where(models.Individual.current.is_(True))):
        if ind.npi:
            emp_keys[ind.cami_employee_id].add(f"npi:{_digits(ind.npi)}")

    return emp_keys


def _key_index(emp_keys: dict[int, set[str]]) -> dict[str, set[int]]:
    key_emps: dict[str, set[int]] = defaultdict(set)
    for emp, keys in emp_keys.items():
        for k in keys:
            key_emps[k].add(emp)
    return key_emps


def _closure(seeds: set[int], emp_keys, key_emps) -> set[int]:
    """Transitive closure: everyone reachable from the seeds via shared keys."""
    seen: set[int] = set()
    stack = list(seeds)
    while stack:
        emp = stack.pop()
        if emp in seen:
            continue
        seen.add(emp)
        for k in emp_keys.get(emp, ()):
            for other in key_emps.get(k, ()):
                if other not in seen:
                    stack.append(other)
    return seen


def _identifiers(group: set[int], emp_keys) -> schemas.ResolveIdentifiers:
    npis: set[str] = set()
    licenses: dict[tuple[str, str], schemas.ResolveLicense] = {}
    for emp in group:
        for k in emp_keys.get(emp, ()):
            if k.startswith("npi:"):
                npis.add(k[4:])
            elif k.startswith("lic:"):
                _, reg, num = k.split(":", 2)
                licenses[(reg, num)] = schemas.ResolveLicense(registry=reg, number=num)
    return schemas.ResolveIdentifiers(
        npi=sorted(npis), licenses=list(licenses.values())
    )


def _names(db: Session, group: set[int]) -> list[schemas.ResolveName]:
    if not group:
        return []
    seen: set[tuple[str | None, str | None]] = set()
    names: list[schemas.ResolveName] = []
    stmt = select(
        models.CredentialMatch.params_first_name,
        models.CredentialMatch.params_last_name,
    ).where(models.CredentialMatch.cami_employee_id.in_(group)).distinct()
    for first, last in db.execute(stmt):
        key = (first, last)
        if key in seen:
            continue
        seen.add(key)
        names.append(schemas.ResolveName(first=first, last=last))
    return names


def _name_candidates(db: Session, first: str, last: str) -> list[int]:
    stmt = (
        select(models.CredentialMatch.cami_employee_id)
        .where(
            func.lower(models.CredentialMatch.params_first_name) == first.lower(),
            func.lower(models.CredentialMatch.params_last_name) == last.lower(),
        )
        .distinct()
    )
    return sorted({row for row in db.scalars(stmt)})


def _all_employees(db: Session) -> set[int]:
    emps: set[int] = set()
    emps |= set(db.scalars(select(models.CredentialMatch.cami_employee_id)))
    emps |= set(db.scalars(select(models.ExclusionMatch.cami_employee_id)))
    emps |= set(db.scalars(select(models.Individual.cami_employee_id)))
    emps |= set(db.scalars(select(models.Entity.cami_employee_id)))
    return emps


def rebuild(db: Session) -> dict[str, int]:
    """Materialize the canonical graph: assign every known employee a canonical
    group id (the smallest cami_employee_id in its strong-id-linked component).
    Full rebuild in one transaction. Run on a schedule behind live syncs."""
    emp_keys = _employee_keys(db)
    key_emps = _key_index(emp_keys)
    all_emps = _all_employees(db)

    seen: set[int] = set()
    rows: list[models.CanonicalEmployee] = []
    groups = 0
    for emp in sorted(all_emps):
        if emp in seen:
            continue
        component = _closure({emp}, emp_keys, key_emps) | {emp}
        canonical = min(component)
        for member in component:
            seen.add(member)
            rows.append(
                models.CanonicalEmployee(cami_employee_id=member, canonical_id=canonical)
            )
        groups += 1

    db.query(models.CanonicalEmployee).delete()
    db.add_all(rows)
    db.commit()
    return {"employees": len(rows), "groups": groups}


def resolve_employee(db: Session, cami_employee_id: int) -> schemas.ResolveOut:
    """Fast per-employee lookup from the materialized graph (no full scan)."""
    row = db.get(models.CanonicalEmployee, cami_employee_id)
    if row is None:
        return schemas.ResolveOut(
            resolved=False, match_basis="none", canonical_employee_ids=[],
            name_only_candidates=[], identifiers=schemas.ResolveIdentifiers(), names=[],
        )
    group = set(
        db.scalars(
            select(models.CanonicalEmployee.cami_employee_id).where(
                models.CanonicalEmployee.canonical_id == row.canonical_id
            )
        )
    )
    emp_keys = _employee_keys(db)
    return schemas.ResolveOut(
        resolved=len(group) > 1,
        match_basis="persisted",
        canonical_employee_ids=sorted(group),
        name_only_candidates=[],
        identifiers=_identifiers(group, emp_keys),
        names=_names(db, group),
    )


def group_for_seeds(db: Session, seeds: set[int], use_persisted: bool = False) -> set[int]:
    """Canonical group for a set of seed employees.

    Live (default): recompute the closure. Persisted: read groups from
    employee_canonical for seeds already materialized, and fall back to a live
    closure only for seeds not yet in the table (freshly synced before the next
    rebuild) — so the fast path never silently drops new records."""
    if not seeds:
        return set()
    if not use_persisted:
        emp_keys = _employee_keys(db)
        return _closure(seeds, emp_keys, _key_index(emp_keys))

    rows = db.execute(
        select(models.CanonicalEmployee.cami_employee_id, models.CanonicalEmployee.canonical_id)
        .where(models.CanonicalEmployee.cami_employee_id.in_(seeds))
    ).all()
    present = {emp: cid for emp, cid in rows}
    result: set[int] = set()
    canonical_ids = set(present.values())
    if canonical_ids:
        result |= set(
            db.scalars(
                select(models.CanonicalEmployee.cami_employee_id).where(
                    models.CanonicalEmployee.canonical_id.in_(canonical_ids)
                )
            )
        )
    unresolved = seeds - present.keys()
    if unresolved:
        emp_keys = _employee_keys(db)
        result |= _closure(unresolved, emp_keys, _key_index(emp_keys))
    return result


def resolve(db: Session, payload: schemas.ResolveIn) -> schemas.ResolveOut:
    emp_keys = _employee_keys(db)
    key_emps = _key_index(emp_keys)

    # Pick the strongest anchor available: NPI, then license.
    anchor_key: str | None = None
    basis = "none"
    if payload.npi and _digits(payload.npi):
        anchor_key = f"npi:{_digits(payload.npi)}"
        basis = "npi"
    elif payload.license_number and payload.registry:
        anchor_key = _license_key(payload.registry, payload.license_number)
        basis = "license"

    if anchor_key is not None:
        seeds = set(key_emps.get(anchor_key, set()))
        group = _closure(seeds, emp_keys, key_emps) if seeds else set()
        return schemas.ResolveOut(
            resolved=bool(group),
            match_basis=basis,
            canonical_employee_ids=sorted(group),
            name_only_candidates=[],
            identifiers=_identifiers(group, emp_keys),
            names=_names(db, group),
        )

    # No strong anchor: a name lookup returns candidates for review, never a
    # merge. resolved is False — the caller must confirm identity.
    if payload.params_first_name and payload.params_last_name:
        candidates = _name_candidates(
            db, payload.params_first_name, payload.params_last_name
        )
        return schemas.ResolveOut(
            resolved=False,
            match_basis="name_only",
            canonical_employee_ids=[],
            name_only_candidates=candidates,
            identifiers=schemas.ResolveIdentifiers(),
            names=[],
        )

    return schemas.ResolveOut(
        resolved=False,
        match_basis="none",
        canonical_employee_ids=[],
        name_only_candidates=[],
        identifiers=schemas.ResolveIdentifiers(),
        names=[],
    )

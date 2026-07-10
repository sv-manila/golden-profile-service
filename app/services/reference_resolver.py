"""Resolve reference rows (registries / exclusion lists) by id or SV-native prefix.

CAMI/SV identifies registries and exclusion lists by a string prefix (e.g.
"nursysny", "oig"). These helpers let callers send that prefix instead of the
Golden Profile's internal integer id; the row is created on first use.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models


def resolve_credential_database_id(
    db: Session, *, id: int | None, prefix: str | None, create: bool = True
) -> int | None:
    if id is not None:
        return id
    if not prefix:
        return None
    key = prefix.strip().lower()
    row = db.scalars(
        select(models.CredentialDatabase).where(
            func.lower(models.CredentialDatabase.prefix) == key
        )
    ).first()
    if row:
        return row.id
    if not create:
        return None
    row = models.CredentialDatabase(prefix=key, description=prefix)
    db.add(row)
    db.flush()
    return row.id


def resolve_exclusion_list_id(
    db: Session, *, id: int | None, prefix: str | None, create: bool = True
) -> int | None:
    if id is not None:
        return id
    if not prefix:
        return None
    key = prefix.strip().lower()
    row = db.scalars(
        select(models.ExclusionList).where(func.lower(models.ExclusionList.prefix) == key)
    ).first()
    if row:
        return row.id
    if not create:
        return None
    row = models.ExclusionList(prefix=key, description=prefix)
    db.add(row)
    db.flush()
    return row.id

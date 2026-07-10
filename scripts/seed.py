"""Seed a demo registry, an exclusion list, and a sample credential match.

Usage:
    ./.venv/Scripts/python.exe -m scripts.seed
"""
from __future__ import annotations

from datetime import date

from app.database import SessionLocal, init_db
from app import models


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        reg = models.CredentialDatabase(prefix="NURSYS-NY", description="Nursys New York", type="LIC", state="NY")
        ex = models.ExclusionList(prefix="OIG-LEIE", description="OIG LEIE", type="EXC")
        db.add_all([reg, ex])
        db.flush()

        cm = models.CredentialMatch(
            cami_employee_id=1001,
            params_first_name="John",
            params_last_name="Smith",
            params_credential_id="RN-55555",
            params_license_type="RN",
            credential_database_id=reg.id,
            current=True,
            match_summary_status="VALID",
            status="ACTIVE",
            expiry_date=date(2099, 1, 1),
            match='{"license":"active"}',
        )
        db.add(cm)
        db.commit()
        print(f"Seeded registry id={reg.id}, exclusion list id={ex.id}, credential_match id={cm.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

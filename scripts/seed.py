"""Seed a sample credential match.

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
        cm = models.CredentialMatch(
            cami_employee_id=1001,
            params_first_name="John",
            params_last_name="Smith",
            params_credential_id="RN-55555",
            params_license_type="RN",
            registry="nursysny",
            match_summary_status="VALID",
            status="ACTIVE",
            expiry_date=date(2099, 1, 1),
            match='{"license":"active"}',
        )
        db.add(cm)
        db.commit()
        print(f"Seeded credential_match id={cm.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

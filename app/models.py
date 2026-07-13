"""SQLAlchemy models mirroring the Golden Profile schema from the CAMI spec.

Type mapping notes (schema targets MySQL/MariaDB, but models stay portable):
  * tinyint(1)  -> Boolean
  * text        -> Text
  * binary(16)  -> LargeBinary(16)
  * datetime    -> DateTime
  * date        -> Date
Timestamp columns default in Python so the same code works on SQLite and MySQL.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    # Naive UTC — matches MySQL DATETIME semantics and works on SQLite.
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# Employees: individuals & entities (versioned snapshots via `current`)
# --------------------------------------------------------------------------- #
class Individual(Base):
    __tablename__ = "individuals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    npi: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cami_employee_id: Mapped[int] = mapped_column(Integer, index=True)
    current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    facility_id: Mapped[str | None] = mapped_column(String(65), nullable=True)
    terminated: Mapped[bool] = mapped_column(Boolean, default=False)
    date_of_termination: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_termination_entered: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    termination_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_of_birth: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    date_hire: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    social_security_num: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ssn_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssn_last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    mmis_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    record_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime, default=_now)
    date_updated: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    last_updated_in_cami: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    names: Mapped[list["IndividualName"]] = relationship(
        back_populates="individual", cascade="all, delete-orphan"
    )
    credentials: Mapped[list["LicensingCredential"]] = relationship(
        back_populates="individual", cascade="all, delete-orphan"
    )
    addresses: Mapped[list["IndividualAddress"]] = relationship(
        back_populates="individual", cascade="all, delete-orphan"
    )


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    npi: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cami_employee_id: Mapped[int] = mapped_column(Integer, index=True)
    current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    facility_id: Mapped[str | None] = mapped_column(String(65), nullable=True)
    terminated: Mapped[bool] = mapped_column(Boolean, default=False)
    date_of_termination: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_termination_entered: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    termination_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    upin: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tin: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tin_last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    mmis_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime, default=_now)
    date_updated: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    last_updated_in_cami: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    names: Mapped[list["EntityName"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    addresses: Mapped[list["EntityAddress"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )


class IndividualName(Base):
    __tablename__ = "individual_names"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    individual_id: Mapped[int] = mapped_column(ForeignKey("individuals.id"), index=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    middle_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    maiden_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime, default=_now)
    date_updated: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    individual: Mapped["Individual"] = relationship(back_populates="names")


class EntityName(Base):
    __tablename__ = "entity_names"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime, default=_now)
    date_updated: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    entity: Mapped["Entity"] = relationship(back_populates="names")


class LicensingCredential(Base):
    __tablename__ = "licensing_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    individual_id: Mapped[int] = mapped_column(ForeignKey("individuals.id"), index=True)
    certification_number: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    certification_state: Mapped[str | None] = mapped_column(String(65), nullable=True)
    license_type_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    license_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    csl_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    csl_state: Mapped[str | None] = mapped_column(String(65), nullable=True)
    dea_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    certification_board: Mapped[str | None] = mapped_column(String(10), nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime, default=_now)
    date_updated: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    individual: Mapped["Individual"] = relationship(back_populates="credentials")


# --------------------------------------------------------------------------- #
# Addresses
# --------------------------------------------------------------------------- #
class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    address1: Mapped[str | None] = mapped_column(String(128), nullable=True)
    address2: Mapped[str | None] = mapped_column(String(128), nullable=True)
    city: Mapped[str | None] = mapped_column(String(65), nullable=True)
    state: Mapped[str | None] = mapped_column(String(65), nullable=True)
    zip: Mapped[str | None] = mapped_column(String(10), nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime, default=_now)
    date_updated: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class IndividualAddress(Base):
    __tablename__ = "individual_addresses"

    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), primary_key=True)
    individual_id: Mapped[int] = mapped_column(ForeignKey("individuals.id"), primary_key=True)

    address: Mapped["Address"] = relationship()
    individual: Mapped["Individual"] = relationship(back_populates="addresses")


class EntityAddress(Base):
    __tablename__ = "entity_addresses"

    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), primary_key=True)

    address: Mapped["Address"] = relationship()
    entity: Mapped["Entity"] = relationship(back_populates="addresses")


# --------------------------------------------------------------------------- #
# Credential matches (+ resolutions)
# --------------------------------------------------------------------------- #
class CredentialMatch(Base):
    __tablename__ = "credential_matches"

    # Composite index serves the idempotency dedup lookup
    # (WHERE cami_credential_match_id = ? AND check_date = ?); its leftmost
    # prefix also covers cami_credential_match_id-only queries.
    __table_args__ = (
        Index("ix_cred_match_dedup", "cami_credential_match_id", "check_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cami_employee_id: Mapped[int] = mapped_column(Integer, index=True)
    cami_credential_match_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    params_first_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    params_middle_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    params_last_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    params_credential_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    params_license_type: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # SV-native registry prefix (e.g. "nursysny", "nyemed"). Denormalized — there
    # is no separate credential_databases table.
    registry: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    match_summary_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    match_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    match: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expiry_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime, default=_now)
    date_updated: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    check_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    resolutions: Mapped[list["CredentialMatchResolution"]] = relationship(
        back_populates="credential_match", cascade="all, delete-orphan"
    )


class CredentialMatchResolution(Base):
    __tablename__ = "credential_match_resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    credential_match_id: Mapped[int] = mapped_column(
        ForeignKey("credential_matches.id"), index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime, default=_now)
    date_updated: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    credential_match: Mapped["CredentialMatch"] = relationship(back_populates="resolutions")


# --------------------------------------------------------------------------- #
# Exclusion matches (+ actions)
# --------------------------------------------------------------------------- #
class ExclusionMatch(Base):
    __tablename__ = "exclusion_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cami_employee_id: Mapped[int] = mapped_column(Integer, index=True)
    cami_match_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    params_first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    params_middle_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    params_last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # SV-native exclusion-list prefix (e.g. "oig", "sam"). Denormalized — there
    # is no separate exclusion_lists table.
    prefix: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    match: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash: Mapped[bytes | None] = mapped_column(LargeBinary(16), nullable=True)
    is_npi_match: Mapped[bool] = mapped_column(Boolean, default=False)
    is_canonical_name_match: Mapped[bool] = mapped_column(Boolean, default=False)
    is_diminutive_name_match: Mapped[bool] = mapped_column(Boolean, default=False)
    is_aka_name_match: Mapped[bool] = mapped_column(Boolean, default=False)
    is_npi_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    is_upin_match: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ssn_match: Mapped[bool] = mapped_column(Boolean, default=False)
    is_license_number_match: Mapped[bool] = mapped_column(Boolean, default=False)
    date_contacted_agency: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime, default=_now)
    date_updated: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    check_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    actions: Mapped[list["ExclusionMatchAction"]] = relationship(
        back_populates="exclusion_match", cascade="all, delete-orphan"
    )


class ExclusionMatchAction(Base):
    __tablename__ = "exclusion_match_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exclusion_match_id: Mapped[int] = mapped_column(
        ForeignKey("exclusion_matches.id"), index=True
    )
    action_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_source_data: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_dob_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ssn_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    is_first_name_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    is_middle_name_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    is_last_name_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    is_address_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    is_npi_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    is_job_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_via: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime, default=_now)
    date_updated: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    exclusion_match: Mapped["ExclusionMatch"] = relationship(back_populates="actions")

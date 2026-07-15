"""Read-only view of the real streamline_local schema.

These Table objects describe columns exactly as they exist in the live CAMI
database (verified with `DESCRIBE <table>` against the local streamline_local
MySQL schema, 2026-07-15) — this service does not own this schema, does not
migrate it, and never writes to it. Only the columns the service actually
reads are declared; the real tables have more columns than listed here.

`metadata` is separate from any ORM Base — there is no declarative mapping,
no relationships, no create_all against MySQL (the real tables already
exist there). `create_all` is used only by tests against a throwaway SQLite
DB shaped like this schema.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

employees = Table(
    "employees",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("first_name", String(100)),
    Column("middle_name", String(100)),
    Column("last_name", String(100)),
    Column("maiden_name", String(100)),
    Column("alt_first_name_1", String(255)),
    Column("alt_last_name_1", String(255)),
    Column("alt_first_name_2", String(255)),
    Column("alt_last_name_2", String(255)),
    Column("alt_first_name_3", String(255)),
    Column("alt_last_name_3", String(255)),
    Column("alt_first_name_4", String(255)),
    Column("alt_last_name_4", String(255)),
    Column("alt_first_name_5", String(255)),
    Column("alt_last_name_5", String(255)),
    Column("business", String(255)),
    Column("npi", Integer),
    Column("certification_number", String(50)),
    Column("certification_state", String(65)),
    Column("ssn_hash", String(255)),
    Column("ssn_last_four", String(4)),
    Column("date_of_birth", Date),
    Column("terminated", Boolean),
)

credential_matches = Table(
    "credential_matches",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("current", Boolean),
    Column("employee_id", Integer, index=True),
    Column("match_context", Text),
    Column("registry", String(255), index=True),
    Column("type", Integer),
    Column("match", Text),
    Column("date_created", DateTime),
    Column("date_updated", DateTime),
    Column("date_resolved", DateTime),
    Column("credential_id", String(255), index=True),
    Column("license_type_id", String(100)),
    Column("last_modified", DateTime),
    Column("expiry_date", Date),
    Column("match_is_valid", Boolean),
    Column("status", String(50)),
    Column("match_summary_status", String(50)),
    Column("match_summary_status_code", Integer),
)

credential_match_resolutions = Table(
    "credential_match_resolutions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("credential_match_id", Integer, index=True),
    Column("note", Text),
    Column("created_at", DateTime),
)

matches = Table(
    "matches",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("employee_id", Integer, index=True),
    Column("exclusion_record_id", Integer, index=True),
    Column("date_contacted_agency", DateTime),
    Column("metadata", JSON),
    Column("date_created", DateTime),
    Column("date_modified", DateTime),
    Column("is_npi_match", Boolean),
    Column("is_canonical_name_match", Boolean),
    Column("is_diminutive_name_match", Boolean),
    Column("is_aka_name_match", Boolean),
    Column("is_npi_mismatch", Boolean),
    Column("is_upin_match", Boolean),
    Column("is_ssn_match", Boolean),
    Column("is_license_number_match", Boolean),
)

match_actions = Table(
    "match_actions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("action_type", String(30)),
    Column("match_id", Integer, index=True),
    Column("note", Text),
    Column("resolution_source_data", String(100)),
    Column("status", Integer),
    Column("is_dob_mismatch", Boolean),
    Column("is_ssn_mismatch", Boolean),
    Column("is_first_name_mismatch", Boolean),
    Column("is_middle_name_mismatch", Boolean),
    Column("is_last_name_mismatch", Boolean),
    Column("is_address_mismatch", Boolean),
    Column("is_npi_mismatch", Boolean),
    Column("is_job_mismatch", Boolean),
    Column("resolved_via", String(20)),
    Column("date_created", DateTime),
)

exclusion_records = Table(
    "exclusion_records",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("exclusion_list_prefix", String(25), index=True),
    Column("match", Text),
    Column("date_created", DateTime),
)

exclusion_lists = Table(
    "exclusion_lists",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("prefix", String(25), index=True),
    Column("description", Text),
)

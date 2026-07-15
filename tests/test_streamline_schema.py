# tests/test_streamline_schema.py
"""The Core schema must expose every table/column the service reads."""
from app import streamline_schema as s


def test_expected_tables_are_present():
    names = set(s.metadata.tables.keys())
    assert names == {
        "employees", "credential_matches", "credential_match_resolutions",
        "matches", "match_actions", "exclusion_records", "exclusion_lists",
    }


def test_employees_columns():
    cols = set(s.employees.c.keys())
    assert {
        "id", "first_name", "last_name", "middle_name", "maiden_name", "business",
        "npi", "certification_number", "certification_state", "ssn_hash",
        "ssn_last_four", "date_of_birth", "terminated",
        "alt_first_name_1", "alt_last_name_1", "alt_first_name_2", "alt_last_name_2",
        "alt_first_name_3", "alt_last_name_3", "alt_first_name_4", "alt_last_name_4",
        "alt_first_name_5", "alt_last_name_5",
    } <= cols


def test_credential_matches_columns():
    cols = set(s.credential_matches.c.keys())
    assert {
        "id", "employee_id", "current", "registry", "type", "match",
        "date_created", "date_updated", "credential_id", "license_type_id",
        "last_modified", "expiry_date", "status", "match_summary_status",
    } <= cols


def test_matches_columns():
    cols = set(s.matches.c.keys())
    assert {
        "id", "employee_id", "exclusion_record_id", "is_npi_match",
        "is_ssn_match", "is_canonical_name_match", "is_diminutive_name_match",
        "is_aka_name_match", "is_license_number_match", "date_created",
    } <= cols

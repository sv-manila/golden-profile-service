# tests/test_resolution.py
"""Entity resolution: unify records for the same real person via a weighted
score. Exact SSN/NPI/license hits alone reach the merge threshold (unchanged
behaviour from the old strong-key closure); name alone never does.
"""
from app.services import resolution


def test_shared_npi_merges_employees(db):
    from tests.conftest import seed_credential_match, seed_employee

    seed_employee(db, id=8801, first_name="Mary", last_name="Res", npi=1990000001)
    seed_employee(db, id=8802, first_name="Mary", last_name="Res", npi=1990000001)
    group = resolution.group_for_seeds(db, {8801})
    assert group == {8801, 8802}


def test_shared_license_merges_employees(db):
    from tests.conftest import seed_credential_match, seed_employee

    seed_employee(db, id=8803, first_name="Ann", last_name="ResB")
    seed_employee(db, id=8804, first_name="Anne", last_name="ResB")
    seed_credential_match(db, employee_id=8803, registry="res-b", credential_id="LIC-B")
    seed_credential_match(db, employee_id=8804, registry="res-b", credential_id="LIC-B")
    group = resolution.group_for_seeds(db, {8803})
    assert group == {8803, 8804}


def test_name_alone_never_merges(db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8805, first_name="John", last_name="MillerRes")
    seed_employee(db, id=8806, first_name="John", last_name="MillerRes")
    group = resolution.group_for_seeds(db, {8805})
    assert group == {8805}  # no DOB, no strong key -> stays separate


def test_name_plus_dob_merges_via_score(db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8842, first_name="Dana", last_name="Wyezz", date_of_birth="1990-05-05")
    seed_employee(db, id=8843, first_name="Dana", last_name="Wyezz", date_of_birth="1990-05-05")
    group = resolution.group_for_seeds(db, {8842})
    assert group == {8842, 8843}


def test_diminutive_name_plus_dob_merges(db):
    from tests.conftest import seed_employee

    # "Bob"/"Robert" is a known diminutive (name_score 0.9) + matching DOB
    # (0.4) = 0.5 + 0.4*... -> min(1.0, 0.9*0.5 + 0.4) = 0.85, at the bar.
    seed_employee(db, id=8850, first_name="Robert", last_name="Diminz", date_of_birth="1985-03-03")
    seed_employee(db, id=8851, first_name="Bob", last_name="Diminz", date_of_birth="1985-03-03")
    group = resolution.group_for_seeds(db, {8850})
    assert group == {8850, 8851}


def test_same_name_different_dob_not_merged(db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8844, first_name="Eve", last_name="Zedzz", date_of_birth="1980-01-01")
    seed_employee(db, id=8845, first_name="Eve", last_name="Zedzz", date_of_birth="1975-02-02")
    group = resolution.group_for_seeds(db, {8844})
    assert 8845 not in group


def test_shared_ssn_hash_merges(db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8840, first_name="Sam", last_name="Ecks", ssn_hash="HASH-SSN-ABC")
    seed_employee(db, id=8841, first_name="Samuel", last_name="Ecks", ssn_hash="HASH-SSN-ABC")
    group = resolution.group_for_seeds(db, {8840})
    assert group == {8840, 8841}


def test_last_four_alone_does_not_merge(db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8846, first_name="Ada", last_name="Onezz", ssn_last_four="1234")
    seed_employee(db, id=8847, first_name="Ida", last_name="Twozz", ssn_last_four="1234")
    group = resolution.group_for_seeds(db, {8846})
    assert group == {8846}


def test_resolution_is_transitive(db):
    from tests.conftest import seed_credential_match, seed_employee

    # A~B share NPI, B~C share a license -> all three resolve together.
    seed_employee(db, id=8807, first_name="Ida", last_name="ResD", npi=1990000009)
    seed_employee(db, id=8808, first_name="Ida", last_name="ResD", npi=1990000009)
    seed_employee(db, id=8809, first_name="I", last_name="ResD")
    seed_credential_match(db, employee_id=8808, registry="res-d2", credential_id="D-SHARED")
    seed_credential_match(db, employee_id=8809, registry="res-d2", credential_id="D-SHARED")
    group = resolution.group_for_seeds(db, {8807})
    assert group == {8807, 8808, 8809}


def test_resolve_employee_endpoint_reports_match_basis(client, db):
    from tests.conftest import seed_employee

    seed_employee(db, id=8860, first_name="Merge", last_name="Basisz", npi=1990000099)
    seed_employee(db, id=8861, first_name="Merge2", last_name="Basisz", npi=1990000099)
    body = client.get("/api/v1/resolve/employee/8860").json()
    assert body["resolved"] is True
    assert sorted(body["canonical_employee_ids"]) == [8860, 8861]
    assert body["match_basis"] == "scored"

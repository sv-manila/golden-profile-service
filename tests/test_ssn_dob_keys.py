# tests/test_ssn_dob_keys.py
"""SSN (hash) and name+DOB as resolution signals, expressed as scores."""
from tests.conftest import seed_employee


def test_shared_ssn_hash_merges(db):
    from app.services import resolution

    seed_employee(db, id=9840, first_name="Sam", last_name="Eckz", ssn_hash="HASH-1")
    seed_employee(db, id=9841, first_name="Samuel", last_name="Eckz", ssn_hash="HASH-1")
    assert resolution.group_for_seeds(db, {9840}) == {9840, 9841}


def test_name_plus_dob_merges(db):
    from app.services import resolution

    seed_employee(db, id=9842, first_name="Dana", last_name="Wyez", date_of_birth="1990-05-05")
    seed_employee(db, id=9843, first_name="Dana", last_name="Wyez", date_of_birth="1990-05-05")
    assert resolution.group_for_seeds(db, {9842}) == {9842, 9843}


def test_same_name_different_dob_not_merged(db):
    from app.services import resolution

    seed_employee(db, id=9844, first_name="Eve", last_name="Zedz", date_of_birth="1980-01-01")
    seed_employee(db, id=9845, first_name="Eve", last_name="Zedz", date_of_birth="1975-02-02")
    assert 9845 not in resolution.group_for_seeds(db, {9844})


def test_last_four_alone_does_not_merge(db):
    from app.services import resolution

    seed_employee(db, id=9846, first_name="Ada", last_name="Onez", ssn_last_four="1234")
    seed_employee(db, id=9847, first_name="Ida", last_name="Twoz", ssn_last_four="1234")
    assert resolution.group_for_seeds(db, {9846}) == {9846}

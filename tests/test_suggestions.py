# tests/test_suggestions.py
"""Fuzzy name-variant SUGGESTIONS — review-only band, never an auto-merge."""
from tests.conftest import seed_employee


def _suggest(client, first, last):
    return client.post("/api/v1/resolve/suggestions",
                       json={"params_first_name": first, "params_last_name": last}).json()


def test_prefix_variant_is_suggested(client, db):
    seed_employee(db, id=8830, first_name="Robert", last_name="Jonez")
    seed_employee(db, id=8831, first_name="Rob", last_name="Jonez")
    ids = [s["cami_employee_id"] for s in _suggest(client, "Robert", "Jonez")["suggestions"]]
    assert 8831 in ids
    assert 8830 not in ids  # the query's own record is never suggested back


def test_already_strong_linked_not_suggested(client, db):
    seed_employee(db, id=8832, first_name="Kathy", last_name="Smithx", npi=1930000001)
    seed_employee(db, id=8833, first_name="Katherine", last_name="Smithx", npi=1930000001)
    ids = [s["cami_employee_id"] for s in _suggest(client, "Kathy", "Smithx")["suggestions"]]
    assert 8833 not in ids  # already merged, not a suggestion


def test_different_last_name_not_suggested(client, db):
    seed_employee(db, id=8834, first_name="Zed", last_name="Alphaz")
    seed_employee(db, id=8835, first_name="Zed", last_name="Betaz")
    ids = [s["cami_employee_id"] for s in _suggest(client, "Zed", "Alphaz")["suggestions"]]
    assert 8835 not in ids


def test_suggestion_carries_score_and_reason(client, db):
    seed_employee(db, id=8836, first_name="Maria", last_name="Santosz")
    seed_employee(db, id=8837, first_name="M", last_name="Santosz")
    sug = _suggest(client, "Maria", "Santosz")["suggestions"]
    hit = [s for s in sug if s["cami_employee_id"] == 8837]
    assert hit and 0 < hit[0]["score"] < 0.85 and hit[0]["reason"]

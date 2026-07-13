"""general_search wired to entity resolution.

A name search pulls in the same person's other records even when spelled
differently, as long as they are linked by a strong id (NPI / license). That is
the artifact's "spelled two ways = one view", now enforced by the service.
"""
import json


def _cm(client, *, emp, registry, cred, first, last, npi=None):
    match = {"npi": npi} if npi else {}
    r = client.post("/api/v1/credential-matches", json={
        "cami_employee_id": emp, "registry": registry,
        "params_first_name": first, "params_last_name": last,
        "params_credential_id": cred, "params_license_type": "RN",
        "match_summary_status": "Valid", "status": "VALID",
        "match": json.dumps(match), "check_date": "2026-06-01T00:00:00",
    })
    assert r.status_code == 201, r.text


def _seed(client):
    # Same person, two employee records, different name spelling, shared NPI,
    # different registries.
    _cm(client, emp=8901, registry="f2-ny", cred="A", first="Maria", last="SantosF2", npi="1970000001")
    _cm(client, emp=8902, registry="f2-ca", cred="B", first="MariaJean", last="SantosF2", npi="1970000001")


def test_resolve_pulls_in_alias_records(client):
    _seed(client)
    body = client.post("/api/v1/search/general", json={
        "params_first_name": "Maria", "params_last_name": "SantosF2",
    }).json()
    regs = sorted(m["registry"] for m in body["credential_matches"])
    # Both registries surface though only one spelling was searched.
    assert regs == ["f2-ca", "f2-ny"]
    assert sorted(body["canonical_employee_ids"]) == [8901, 8902]


def test_resolve_off_keeps_exact_name_only(client):
    _seed(client)
    body = client.post("/api/v1/search/general", json={
        "params_first_name": "Maria", "params_last_name": "SantosF2",
        "resolve": False,
    }).json()
    regs = [m["registry"] for m in body["credential_matches"]]
    # Only the exact-name record (8901 / f2-ny); alias not merged.
    assert regs == ["f2-ny"]

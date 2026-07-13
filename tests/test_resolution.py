"""Entity resolution: unify records for the same real person.

The canonical grouping links cami_employee_ids that share a STRONG identifier
(NPI, or registry+license number). Name alone never merges — that is the
artifact's "two John Millers" safety rule. This is what makes "one trusted view,
even spelled two ways" literally true rather than relying on the caller.
"""


def _cm(client, *, emp, registry, cred, first, last, npi=None):
    match = {"npi": npi} if npi else {}
    r = client.post("/api/v1/credential-matches", json={
        "cami_employee_id": emp, "registry": registry,
        "params_first_name": first, "params_last_name": last,
        "params_credential_id": cred, "params_license_type": "RN",
        "match_summary_status": "Valid", "status": "VALID",
        "match": __import__("json").dumps(match),
        "check_date": "2026-06-01T00:00:00",
    })
    assert r.status_code == 201, r.text


def test_shared_npi_merges_employees(client):
    _cm(client, emp=8801, registry="res-a1", cred="L1", first="Mary", last="Res", npi="1990000001")
    _cm(client, emp=8802, registry="res-a2", cred="L2", first="Mary", last="Res", npi="1990000001")
    body = client.post("/api/v1/resolve", json={"npi": "1990000001"}).json()
    assert body["resolved"] is True
    assert body["match_basis"] == "npi"
    assert sorted(body["canonical_employee_ids"]) == [8801, 8802]


def test_shared_license_merges_employees(client):
    _cm(client, emp=8803, registry="res-b", cred="LIC-B", first="Ann", last="ResB")
    _cm(client, emp=8804, registry="res-b", cred="LIC-B", first="Anne", last="ResB")
    body = client.post("/api/v1/resolve",
                       json={"registry": "res-b", "license_number": "LIC-B"}).json()
    assert body["resolved"] is True
    assert body["match_basis"] == "license"
    assert sorted(body["canonical_employee_ids"]) == [8803, 8804]


def test_name_alone_never_merges(client):
    # Two different people, same name, no shared strong id -> candidates, NOT merged.
    _cm(client, emp=8805, registry="res-c1", cred="C-1", first="John", last="MillerRes")
    _cm(client, emp=8806, registry="res-c2", cred="C-2", first="John", last="MillerRes")
    body = client.post("/api/v1/resolve",
                       json={"params_first_name": "John", "params_last_name": "MillerRes"}).json()
    assert body["resolved"] is False
    assert body["match_basis"] == "name_only"
    assert body["canonical_employee_ids"] == []
    assert sorted(body["name_only_candidates"]) == [8805, 8806]


def test_resolution_is_transitive(client):
    # A~B share NPI, B~C share a license -> all three resolve together.
    _cm(client, emp=8807, registry="res-d1", cred="D-1", first="Ida", last="ResD", npi="1990000009")
    _cm(client, emp=8808, registry="res-d2", cred="D-SHARED", first="Ida", last="ResD", npi="1990000009")
    _cm(client, emp=8809, registry="res-d2", cred="D-SHARED", first="I.", last="ResD")
    body = client.post("/api/v1/resolve", json={"npi": "1990000009"}).json()
    assert sorted(body["canonical_employee_ids"]) == [8807, 8808, 8809]

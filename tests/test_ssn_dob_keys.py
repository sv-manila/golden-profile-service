"""SSN (hash) and name+DOB as strong entity-resolution keys.

SSN merges on the salted hash (never the last-four). Name alone never merges,
but full name + date of birth is discriminating enough to link.
"""


def _ind(client, *, emp, first, last, ssn_hash=None, dob=None, npi=None):
    payload = {"cami_employee_id": emp, "names": [{"first_name": first, "last_name": last}]}
    if ssn_hash:
        payload["ssn_hash"] = ssn_hash
    if dob:
        payload["date_of_birth"] = dob
    if npi:
        payload["npi"] = npi
    r = client.post("/api/v1/employees/individuals", json=payload)
    assert r.status_code == 201, r.text


def _group(client, emp):
    client.post("/api/v1/resolve/rebuild")
    return set(client.get(f"/api/v1/resolve/employee/{emp}").json()["canonical_employee_ids"])


def test_shared_ssn_hash_merges(client):
    _ind(client, emp=8840, first="Sam", last="Ecks", ssn_hash="HASH-SSN-ABC")
    _ind(client, emp=8841, first="Samuel", last="Ecks", ssn_hash="HASH-SSN-ABC")
    assert {8840, 8841} <= _group(client, 8840)


def test_name_plus_dob_merges(client):
    _ind(client, emp=8842, first="Dana", last="Wyezz", dob="1990-05-05")
    _ind(client, emp=8843, first="Dana", last="Wyezz", dob="1990-05-05")
    assert {8842, 8843} <= _group(client, 8842)


def test_same_name_different_dob_not_merged(client):
    _ind(client, emp=8844, first="Eve", last="Zedzz", dob="1980-01-01")
    _ind(client, emp=8845, first="Eve", last="Zedzz", dob="1975-02-02")
    assert 8845 not in _group(client, 8844)


def test_last_four_alone_does_not_merge(client):
    # Same SSN last-four, no hash -> NOT a strong key (too common to merge on).
    _ind(client, emp=8846, first="Ada", last="Onezz")
    _ind(client, emp=8847, first="Ida", last="Twozz")
    client.post("/api/v1/credential-matches", json={
        "cami_employee_id": 8846, "registry": "ssn-a", "params_credential_id": "X1",
        "params_first_name": "Ada", "params_last_name": "Onezz",
        "match_summary_status": "Valid", "status": "VALID", "match": "{}",
    })
    assert 8847 not in _group(client, 8846)

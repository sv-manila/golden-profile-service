"""End-to-end tests covering the four Golden Profile processes."""


def _make_registry(client, prefix="NURSYS"):
    r = client.post("/api/v1/credential-databases", json={"prefix": prefix, "description": prefix})
    assert r.status_code == 201
    return r.json()["id"]


def _make_exclusion_list(client, prefix="OIG"):
    r = client.post("/api/v1/exclusion-lists", json={"prefix": prefix, "description": prefix})
    assert r.status_code == 201
    return r.json()["id"]


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_individual_sync_versions_snapshots(client):
    payload = {
        "cami_employee_id": 5001,
        "npi": 1234567890,
        "job_title": "RN",
        "social_security_num": "123-45-6789",
        "names": [{"first_name": "Jane", "last_name": "Doe"}],
        "credentials": [{"license_type": "RN", "certification_number": "RN123", "certification_state": "NY"}],
        "addresses": [{"address1": "1 Main St", "city": "Albany", "state": "NY", "zip": "12207"}],
    }
    r1 = client.post("/api/v1/employees/individuals", json=payload)
    assert r1.status_code == 201
    first = r1.json()
    assert first["current"] is True
    assert first["superseded_ids"] == []

    # Re-sync same employee -> new current snapshot, old one superseded.
    r2 = client.post("/api/v1/employees/individuals", json=payload)
    second = r2.json()
    assert second["id"] != first["id"]
    assert second["superseded_ids"] == [first["id"]]


def test_entity_sync(client):
    payload = {
        "cami_employee_id": 7001,
        "tin": "998877665",
        "names": [{"name": "Acme Health LLC"}],
        "addresses": [{"address1": "5 Corp Way", "city": "NYC", "state": "NY", "zip": "10001"}],
    }
    r = client.post("/api/v1/employees/entities", json=payload)
    assert r.status_code == 201
    assert r.json()["employee_type"] == "entity"


def test_search_returns_valid_cached_match(client):
    reg = _make_registry(client, "NURSYS-NY")
    client.post(
        "/api/v1/credential-matches",
        json={
            "cami_employee_id": 8001,
            "params_first_name": "John",
            "params_last_name": "Smith",
            "params_credential_id": "RN-55555",
            "params_license_type": "RN",
            "credential_database_id": reg,
            "match_summary_status": "VALID",
            "status": "ACTIVE",
            "expiry_date": "2099-01-01",
            "match": "{\"license\":\"active\"}",
        },
    )
    r = client.post(
        "/api/v1/search/credential",
        json={
            "credential_database_id": reg,
            "params_credential_id": "RN-55555",
            "params_license_type": "RN",
            "params_first_name": "John",
            "params_last_name": "Smith",
        },
    )
    body = r.json()
    assert body["found"] is True
    assert body["action"] == "return_result"
    assert body["credential_match"]["params_credential_id"] == "RN-55555"


def test_search_expired_match_triggers_scrape(client):
    reg = _make_registry(client, "NURSYS-EXP")
    client.post(
        "/api/v1/credential-matches",
        json={
            "cami_employee_id": 8002,
            "params_credential_id": "RN-EXP",
            "params_license_type": "RN",
            "credential_database_id": reg,
            "match_summary_status": "VALID",
            "expiry_date": "2000-01-01",
        },
    )
    r = client.post(
        "/api/v1/search/credential",
        json={"credential_database_id": reg, "params_credential_id": "RN-EXP", "params_license_type": "RN",
              "params_first_name": "Any", "params_last_name": "Name"},
    )
    assert r.json()["action"] == "trigger_scrape"


def test_search_name_mismatch_auto_resolves(client):
    reg = _make_registry(client, "NURSYS-NM")
    # Match stored under a different name, but carrying a resolution.
    client.post(
        "/api/v1/credential-matches",
        json={
            "cami_employee_id": 8003,
            "params_first_name": "Robert",
            "params_last_name": "Jones",
            "params_credential_id": "RN-77777",
            "params_license_type": "RN",
            "credential_database_id": reg,
            "match_summary_status": "VALID",
            "expiry_date": "2099-01-01",
            "resolutions": [{"note": "Confirmed same person: Bob vs Robert"}],
        },
    )
    # Search with a mismatching first name.
    r = client.post(
        "/api/v1/search/credential",
        json={
            "credential_database_id": reg,
            "params_credential_id": "RN-77777",
            "params_license_type": "RN",
            "params_first_name": "Bob",
            "params_last_name": "Jones",
        },
    )
    body = r.json()
    assert body["action"] == "auto_resolve_name_mismatch"
    assert body["resolution"]["note"].startswith("Confirmed")


def test_search_no_match_triggers_scrape(client):
    reg = _make_registry(client, "EMPTY-REG")
    r = client.post(
        "/api/v1/search/credential",
        json={"credential_database_id": reg, "params_credential_id": "NOPE", "params_license_type": "RN",
              "params_first_name": "No", "params_last_name": "Match"},
    )
    assert r.json() == {
        "found": False,
        "action": "trigger_scrape",
        "source": "golden_profile",
        "reason": "No valid match or resolution in Golden Profile; trigger bot scrape.",
        "credential_match": None,
        "resolution": None,
    }


def test_prefix_based_sync_and_search(client):
    # No registry created up front; sync by SV-native prefix auto-creates it.
    r = client.post(
        "/api/v1/credential-matches",
        json={
            "cami_employee_id": 8500,
            "registry_prefix": "NursysNY",
            "params_credential_id": "RN-PFX",
            "params_license_type": "RN",
            "params_first_name": "Amy",
            "params_last_name": "Poe",
            "match_summary_status": "ACTIVE",
            "expiry_date": "2099-01-01",
        },
    )
    assert r.status_code == 201
    # Search by the same prefix (case-insensitive) finds it.
    r2 = client.post(
        "/api/v1/search/credential",
        json={
            "registry_prefix": "nursysny",
            "params_credential_id": "RN-PFX",
            "params_license_type": "RN",
            "params_first_name": "Amy",
            "params_last_name": "Poe",
        },
    )
    assert r2.json()["action"] == "return_result"


def test_search_unknown_prefix_triggers_scrape(client):
    r = client.post(
        "/api/v1/search/credential",
        json={"registry_prefix": "does-not-exist", "params_credential_id": "X",
              "params_first_name": "Un", "params_last_name": "Known"},
    )
    assert r.json()["action"] == "trigger_scrape"


def test_missing_registry_is_rejected(client):
    r = client.post("/api/v1/search/credential",
                    json={"params_credential_id": "X", "params_first_name": "A", "params_last_name": "B"})
    assert r.status_code == 422


def test_missing_name_is_rejected(client):
    reg = _make_registry(client, "NAME-REQ")
    # No first name
    r1 = client.post("/api/v1/search/credential",
                     json={"credential_database_id": reg, "params_last_name": "Doe"})
    assert r1.status_code == 422
    # No last name
    r2 = client.post("/api/v1/search/credential",
                     json={"credential_database_id": reg, "params_first_name": "Jane"})
    assert r2.status_code == 422
    # Blank names are rejected too
    r3 = client.post("/api/v1/search/credential",
                     json={"credential_database_id": reg, "params_first_name": " ", "params_last_name": " "})
    assert r3.status_code == 422


def test_exclusion_match_sync(client):
    ex = _make_exclusion_list(client, "OIG-LEIE")
    r = client.post(
        "/api/v1/exclusion-matches",
        json={
            "cami_employee_id": 9001,
            "params_first_name": "Jane",
            "params_last_name": "Doe",
            "exclusion_list_id": ex,
            "match": "{\"hit\":true}",
            "is_canonical_name_match": True,
            "actions": [{"action_type": "review", "note": "pending", "is_dob_mismatch": True}],
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["exclusion_list_id"] == ex

    # Re-sync supersedes.
    r2 = client.post(
        "/api/v1/exclusion-matches",
        json={"cami_employee_id": 9001, "exclusion_list_id": ex, "match": "{}"},
    )
    assert r2.json()["superseded_ids"] == [body["id"]]


# --------------------------------------------------------------------------- #
# General (name-based) search
# --------------------------------------------------------------------------- #
def _seed_general(client, tag):
    """Seed 2 state-specific registries + 2 credential matches + 1 exclusion for
    a unique name (isolates tests sharing the session-scoped DB)."""
    first, last = "Gena", f"Searcher{tag}"
    ny = client.post("/api/v1/credential-databases",
                     json={"prefix": f"GEN{tag}-NY", "description": "Gen NY", "state": "NY"}).json()["id"]
    ca = client.post("/api/v1/credential-databases",
                     json={"prefix": f"GEN{tag}-CA", "description": "Gen CA", "state": "CA"}).json()["id"]
    client.post("/api/v1/credential-matches", json={
        "cami_employee_id": 9100, "credential_database_id": ny,
        "params_first_name": first, "params_last_name": last,
        "params_credential_id": "NY-111", "params_license_type": "RN",
        "match_summary_status": "Valid", "status": "VALID", "match": "{\"response_code\":2}",
    })
    client.post("/api/v1/credential-matches", json={
        "cami_employee_id": 9100, "credential_database_id": ca,
        "params_first_name": first, "params_last_name": last,
        "params_credential_id": "CA-222", "params_license_type": "RN",
        "match_summary_status": "Invalid - Expired", "status": "1", "match": "{\"response_code\":2}",
    })
    ex = _make_exclusion_list(client, f"GEN{tag}-OIG")
    client.post("/api/v1/exclusion-matches", json={
        "cami_employee_id": 9100, "exclusion_list_id": ex,
        "params_first_name": first, "params_last_name": last,
        "match": "{\"hit\":true}", "is_npi_match": True,
    })
    return first, last


def test_general_search_returns_matches_per_registry_and_exclusions(client):
    first, last = _seed_general(client, "A")
    r = client.post("/api/v1/search/general",
                    json={"params_first_name": first, "params_last_name": last})
    assert r.status_code == 200
    body = r.json()
    # One credential match per registry (2), plus the exclusion match.
    assert len(body["credential_matches"]) == 2
    assert sorted(m["registry_state"] for m in body["credential_matches"]) == ["CA", "NY"]
    assert len(body["exclusion_matches"]) == 1
    assert body["exclusion_matches"][0]["is_npi_match"] is True


def test_general_search_filters_by_license_number(client):
    first, last = _seed_general(client, "B")
    r = client.post("/api/v1/search/general",
                    json={"params_first_name": first, "params_last_name": last,
                          "params_credential_id": "NY-111"})
    body = r.json()
    assert len(body["credential_matches"]) == 1
    assert body["credential_matches"][0]["params_credential_id"] == "NY-111"
    # Exclusions are unaffected by the credential filters.
    assert len(body["exclusion_matches"]) == 1


def test_general_search_filters_by_certification_state(client):
    first, last = _seed_general(client, "C")
    r = client.post("/api/v1/search/general",
                    json={"params_first_name": first, "params_last_name": last,
                          "params_certification_state": "ny"})
    body = r.json()
    assert len(body["credential_matches"]) == 1
    assert body["credential_matches"][0]["registry_state"] == "NY"


def test_general_search_requires_name(client):
    assert client.post("/api/v1/search/general", json={"params_first_name": "OnlyFirst"}).status_code == 422
    assert client.post("/api/v1/search/general", json={"params_last_name": "OnlyLast"}).status_code == 422
    assert client.post("/api/v1/search/general",
                       json={"params_first_name": " ", "params_last_name": " "}).status_code == 422


def test_general_search_hides_expired_by_default(client):
    reg = _make_registry(client, "EXP-REG")
    client.post("/api/v1/credential-matches", json={
        "cami_employee_id": 9200, "credential_database_id": reg,
        "params_first_name": "Exp", "params_last_name": "Ired",
        "params_credential_id": "E-1", "status": "VALID",
        "match_summary_status": "Valid", "expiry_date": "2000-01-01",
        "match": "{\"response_code\":2}",
    })
    # Default: expired result is hidden.
    r = client.post("/api/v1/search/general",
                    json={"params_first_name": "Exp", "params_last_name": "Ired"})
    assert len(r.json()["credential_matches"]) == 0
    # include_expired=true: shown.
    r2 = client.post("/api/v1/search/general",
                     json={"params_first_name": "Exp", "params_last_name": "Ired", "include_expired": True})
    assert len(r2.json()["credential_matches"]) == 1


def test_general_search_exclude_no_matches(client):
    reg = _make_registry(client, "NM-REG")
    client.post("/api/v1/credential-matches", json={
        "cami_employee_id": 9300, "credential_database_id": reg,
        "params_first_name": "Noma", "params_last_name": "Tch",
        "params_credential_id": "N-1", "status": "2",   # CredentialMatch::NO_MATCH
        "match_summary_status": "No Match", "match": "{\"response_code\":1}",
    })
    # Default: no-match is included.
    r = client.post("/api/v1/search/general",
                    json={"params_first_name": "Noma", "params_last_name": "Tch"})
    assert len(r.json()["credential_matches"]) == 1
    # exclude_no_matches=true: filtered out.
    r2 = client.post("/api/v1/search/general",
                     json={"params_first_name": "Noma", "params_last_name": "Tch", "exclude_no_matches": True})
    assert len(r2.json()["credential_matches"]) == 0

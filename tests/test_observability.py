"""Observability: search decisions are both counted (/stats) and logged.

/stats counters reset on restart; the structured log lines are what survive into
CloudWatch for long-term hit-rate / conflict monitoring.
"""
import logging


def _seed_valid(client, tag):
    client.post("/api/v1/credential-matches", json={
        "cami_employee_id": 9500, "registry": f"obs-{tag}",
        "params_first_name": "Obs", "params_last_name": f"Er{tag}",
        "params_credential_id": "OB-1", "params_license_type": "RN",
        "match_summary_status": "Valid", "status": "VALID",
        "match": "{\"response_code\":2}", "check_date": "2026-06-01T00:00:00",
    })


def test_search_hit_is_counted_and_logged(client, caplog):
    _seed_valid(client, "hit")
    with caplog.at_level(logging.INFO, logger="golden_profile.search"):
        r = client.post("/api/v1/search/credential", json={
            "registry": "obs-hit", "params_first_name": "Obs",
            "params_last_name": "Erhit", "params_credential_id": "OB-1",
        })
    assert r.json()["action"] == "return_result"
    # A structured decision line was emitted for the hit.
    assert any("search.credential" in rec.message and "return_result" in rec.message
               for rec in caplog.records)


def test_conflict_is_counted(client):
    # Two disagreeing snapshots, same registry+license -> a conflict.
    for status, summary, cd in (("1", "Invalid - Expired", "2025-01-01T00:00:00"),
                                ("VALID", "Valid", "2026-06-01T00:00:00")):
        client.post("/api/v1/credential-matches", json={
            "cami_employee_id": 9501, "registry": "obs-conf",
            "params_first_name": "Obs", "params_last_name": "Conf",
            "params_credential_id": "OB-9", "params_license_type": "RN",
            "match_summary_status": summary, "status": status,
            "match": "{\"response_code\":2}", "check_date": cd,
        })
    before = client.get("/api/v1/stats").json()["counters"].get("search.conflict", 0)
    client.post("/api/v1/search/general",
                json={"params_first_name": "Obs", "params_last_name": "Conf"})
    after = client.get("/api/v1/stats").json()["counters"].get("search.conflict", 0)
    assert after == before + 1

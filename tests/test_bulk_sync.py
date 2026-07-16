"""Bulk credential-match sync endpoint."""
from __future__ import annotations

import json


def _item(emp_id: int, registry: str):
    return {
        "cami_employee_id": emp_id,
        "registry": registry,
        "params_first_name": "Bulk",
        "params_last_name": f"Person{emp_id}",
        "params_credential_id": f"L{emp_id}",
        "params_license_type": "RN",
        "status": "VALID",
        "match": json.dumps({"response_code": "0"}),
    }


def test_bulk_sync_inserts_all(client):
    payload = {"items": [_item(601, "bulkreg"), _item(602, "bulkreg"), _item(603, "bulkreg")]}
    resp = client.post("/api/v1/credential-matches/bulk", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["count"] == 3
    assert len(body["results"]) == 3
    assert all(r["id"] for r in body["results"])
    # All carry the same registry string.
    registries = {r["registry"] for r in body["results"]}
    assert registries == {"bulkreg"}


def test_bulk_sync_appends_new_snapshot(client):
    # First bulk insert, then a second sync of the same logical credential.
    first = client.post("/api/v1/credential-matches/bulk", json={"items": [_item(610, "bulkreg2")]})
    resp = client.post("/api/v1/credential-matches/bulk", json={"items": [_item(610, "bulkreg2")]})
    body = resp.json()
    assert body["count"] == 1
    # Snapshots are append-only: the re-sync inserts a distinct new row.
    assert body["results"][0]["id"] != first.json()["results"][0]["id"]


def test_bulk_sync_rejects_empty(client):
    resp = client.post("/api/v1/credential-matches/bulk", json={"items": []})
    assert resp.status_code == 422

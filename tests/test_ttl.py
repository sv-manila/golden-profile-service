"""Cache-freshness (TTL) behaviour of the credential search."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.services import search as search_service


def _iso_days_ago(days: int) -> str:
    stamp = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    return stamp.strftime("%Y-%m-%d %H:%M:%S")


def _seed(client, *, check_days_ago: int, registry="nursysttl", first="Jane", last="Doe"):
    body = {
        "cami_employee_id": 501,
        "registry_prefix": registry,
        "params_first_name": first,
        "params_last_name": last,
        "params_credential_id": "L-TTL-1",
        "params_license_type": "RN",
        "status": "VALID",
        "match": json.dumps({"response_code": "0", "npi": "1234567890"}),
        "check_date": _iso_days_ago(check_days_ago),
    }
    resp = client.post("/api/v1/credential-matches", json=body)
    assert resp.status_code == 201, resp.text


def _search(client, registry="nursysttl", first="Jane", last="Doe"):
    return client.post(
        "/api/v1/search/credential",
        json={
            "registry_prefix": registry,
            "params_first_name": first,
            "params_last_name": last,
            "params_credential_id": "L-TTL-1",
            "params_license_type": "RN",
        },
    )


def test_ttl_disabled_serves_any_age(client, monkeypatch):
    monkeypatch.setattr(search_service, "get_settings", lambda: Settings(credential_ttl_days=0))
    _seed(client, check_days_ago=400)
    body = _search(client).json()
    assert body["found"] is True
    assert body["action"] == "return_result"
    assert body["age_days"] >= 399


def test_ttl_stale_match_triggers_scrape(client, monkeypatch):
    monkeypatch.setattr(search_service, "get_settings", lambda: Settings(credential_ttl_days=30))
    _seed(client, check_days_ago=400, registry="nursysttl2")
    body = _search(client, registry="nursysttl2").json()
    assert body["found"] is False
    assert body["action"] == "trigger_scrape"
    assert "stale" in body["reason"].lower()
    assert body["age_days"] >= 399


def test_ttl_fresh_match_still_served(client, monkeypatch):
    monkeypatch.setattr(search_service, "get_settings", lambda: Settings(credential_ttl_days=30))
    _seed(client, check_days_ago=5, registry="nursysttl3")
    body = _search(client, registry="nursysttl3").json()
    assert body["found"] is True
    assert body["action"] == "return_result"


def test_ttl_per_registry_override(client, monkeypatch):
    # Global TTL is generous, but this registry is overridden to 1 day.
    monkeypatch.setattr(
        search_service,
        "get_settings",
        lambda: Settings(credential_ttl_days=365, credential_ttl_overrides='{"nursysttl4": 1}'),
    )
    _seed(client, check_days_ago=10, registry="nursysttl4")
    body = _search(client, registry="nursysttl4").json()
    assert body["found"] is False
    assert body["action"] == "trigger_scrape"

"""Cross-language contract: the search payload the CAMI (PHP) gateway consumes.

These assertions pin the exact shape that
`client/app/Services/GoldenProfile/GoldenProfileGateway::lookupCredentialData()`
reads. If the service changes any of these keys, this test fails BEFORE the
change silently breaks search-before-scrape in production (the failure mode is
invisible — CAMI just falls back to scraping on every check).

Contract, per the PHP:
  * top-level `found` must be truthy for a usable result
  * top-level `action` must be one of return_result / auto_resolve_name_mismatch
  * `credential_match.match` must be a JSON string decoding to an object that
    contains `response_code` (the gateway's `array_key_exists('response_code')`
    gate) — otherwise the hit is discarded and CAMI scrapes.
"""
from __future__ import annotations

import json

USABLE_ACTIONS = {"return_result", "auto_resolve_name_mismatch"}


def _seed(client):
    client.post(
        "/api/v1/credential-matches",
        json={
            "cami_employee_id": 801,
            "registry_prefix": "contractreg",
            "params_first_name": "Contract",
            "params_last_name": "Case",
            "params_credential_id": "L801",
            "params_license_type": "RN",
            "status": "VALID",
            # A representative scraper-shaped blob — response_code is the key the
            # gateway requires to treat the cached result as usable.
            "match": json.dumps(
                {"response_code": "0", "npi": "1234567890", "license_status": "Active"}
            ),
        },
    )


def test_return_result_matches_gateway_contract(client):
    _seed(client)
    resp = client.post(
        "/api/v1/search/credential",
        json={
            "registry_prefix": "contractreg",
            "params_first_name": "Contract",
            "params_last_name": "Case",
            "params_credential_id": "L801",
            "params_license_type": "RN",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # 1. Usability gate the gateway checks first.
    assert body["found"] is True
    assert body["action"] in USABLE_ACTIONS

    # 2. credential_match + its `match` string must be present.
    assert body["credential_match"] is not None
    encoded = body["credential_match"]["match"]
    assert isinstance(encoded, str), "gateway does json_decode() on a string"

    # 3. Decodes to an object carrying response_code.
    decoded = json.loads(encoded)
    assert isinstance(decoded, dict)
    assert "response_code" in decoded, "gateway discards hits without response_code"


def test_trigger_scrape_shape_is_stable(client):
    # A miss must still carry found=False + action, so the gateway's
    # `empty($result['found'])` short-circuit works.
    resp = client.post(
        "/api/v1/search/credential",
        json={
            "registry_prefix": "unknown-contract-registry",
            "params_first_name": "No",
            "params_last_name": "Body",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is False
    assert body["action"] == "trigger_scrape"

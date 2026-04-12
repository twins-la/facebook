"""LOGGING.md §3.2 conformance smoke test for the Facebook twin.

Exercises a cross-section of operations (twin plane tenant/app creation
and unauth OAuth denial) and asserts every emitted record carries
every required field with the required types.
"""

REQUIRED_FIELDS = {
    "timestamp", "twin", "tenant_id", "correlation_id",
    "plane", "operation", "resource", "outcome", "reason", "details",
}
VALID_PLANES = {"twin", "control", "data", "runtime"}
VALID_OUTCOMES = {"success", "failure"}


def _assert_record_conforms(rec):
    assert REQUIRED_FIELDS.issubset(rec.keys()), rec
    assert rec["timestamp"].endswith("Z")
    assert rec["twin"] == "facebook"
    assert isinstance(rec["tenant_id"], str) and rec["tenant_id"]
    assert isinstance(rec["correlation_id"], str) and rec["correlation_id"]
    assert rec["plane"] in VALID_PLANES, rec
    assert isinstance(rec["operation"], str) and rec["operation"]
    assert rec["resource"] is None or (
        isinstance(rec["resource"], dict)
        and set(rec["resource"].keys()) == {"type", "id"}
    )
    assert rec["outcome"] in VALID_OUTCOMES, rec
    if rec["outcome"] == "failure":
        assert isinstance(rec["reason"], str) and rec["reason"].strip()
    assert isinstance(rec["details"], dict)


def test_tenant_and_app_creation_logs_conform(client, tenant_headers, admin_headers):
    # twin.tenant.create ran when the `tenant` fixture was created — that
    # path is the tenant store, not the twin's append_log. Drive creation
    # through the Twin Plane instead.
    resp = client.post("/_twin/tenants", json={"friendly_name": "Conformance"})
    assert resp.status_code == 201
    resp = client.post(
        "/_twin/apps",
        headers=tenant_headers,
        json={"name": "Conform App", "redirect_uris": ["https://x.test/cb"]},
    )
    assert resp.status_code == 201
    logs = client.get("/_twin/logs", headers=admin_headers).get_json()["logs"]
    assert logs
    ops = {l["operation"] for l in logs}
    assert {"twin.tenant.create", "twin.app.create"}.issubset(ops)
    for rec in logs:
        _assert_record_conforms(rec)


def test_correlation_id_is_echoed(client):
    resp = client.get("/_twin/health", headers={"X-Correlation-Id": "caller-xyz"})
    assert resp.headers.get("X-Correlation-Id") == "caller-xyz"

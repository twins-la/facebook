"""Twin Plane: health, scenarios, references, settings, apps, users, tokens, logs."""

import base64


def test_health(client):
    r = client.get("/_twin/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["twin"] == "facebook"


def test_scenarios_lists_facebook_login(client):
    r = client.get("/_twin/scenarios")
    assert r.status_code == 200
    names = [s["name"] for s in r.get_json()["scenarios"]]
    assert "facebook-login" in names


def test_references_has_retrieval_dates(client):
    r = client.get("/_twin/references")
    body = r.get_json()
    assert r.status_code == 200
    assert body["references"], "references must not be empty"
    for ref in body["references"]:
        assert ref["url"].startswith("https://")
        assert ref["retrieved"]
        assert ref["title"]


def test_settings_reports_supported_versions(client):
    r = client.get("/_twin/settings")
    body = r.get_json()
    assert "v19.0" in body["supported_versions"]
    assert "v21.0" in body["supported_versions"]


def test_create_app_requires_admin(client):
    r = client.post("/_twin/apps", json={"redirect_uris": ["https://x/cb"]})
    assert r.status_code == 401


def test_create_app_requires_redirect_uris(client, admin_headers):
    r = client.post("/_twin/apps", json={}, headers=admin_headers)
    assert r.status_code == 400


def test_create_and_get_app(client, admin_headers):
    r = client.post("/_twin/apps", json={
        "name": "Demo", "redirect_uris": ["https://client/cb"],
    }, headers=admin_headers)
    assert r.status_code == 201
    full = r.get_json()
    assert "app_id" in full and "app_secret" in full

    r2 = client.get(f"/_twin/apps/{full['app_id']}", headers=admin_headers)
    assert r2.status_code == 200
    public = r2.get_json()
    assert public["app_id"] == full["app_id"]
    assert "app_secret" not in public


def test_delete_app(client, admin_headers, test_app_record):
    r = client.delete(f"/_twin/apps/{test_app_record['app_id']}", headers=admin_headers)
    assert r.status_code == 204


def test_create_user_and_update(client, admin_headers, test_app_record):
    r = client.post("/_twin/users", json={
        "app_id": test_app_record["app_id"],
        "name": "Bob", "email": "bob@example.com",
        "granted_scopes": ["email"],
    }, headers=admin_headers)
    assert r.status_code == 201
    u = r.get_json()

    r2 = client.patch(
        f"/_twin/apps/{test_app_record['app_id']}/users/{u['fb_id']}",
        json={"granted_scopes": ["public_profile"]},  # email revoked
        headers=admin_headers,
    )
    assert r2.status_code == 200
    assert "email" not in r2.get_json()["granted_scopes"]


def test_create_user_requires_app_id(client, admin_headers):
    r = client.post("/_twin/users", json={"name": "X"}, headers=admin_headers)
    assert r.status_code == 400


def test_create_user_rejects_unknown_app_id(client, admin_headers):
    r = client.post("/_twin/users", json={
        "app_id": "000000000000000", "name": "X",
    }, headers=admin_headers)
    assert r.status_code == 404


def test_tenant_can_mint_token(client, tenant_headers, test_app_record, test_user):
    r = client.post("/_twin/tokens", json={
        "app_id": test_app_record["app_id"],
        "fb_id": test_user["fb_id"], "scopes": ["email"],
    }, headers=tenant_headers)
    assert r.status_code == 201
    body = r.get_json()
    assert body["access_token"].startswith("EAA")
    assert body["token_type"] == "bearer"


def test_admin_requires_app_id_for_mint(client, admin_headers, test_user):
    r = client.post("/_twin/tokens", json={"fb_id": test_user["fb_id"]},
                    headers=admin_headers)
    assert r.status_code == 400


def test_logs_admin_vs_tenant(client, admin_headers, tenant, tenant_headers, test_app_record, test_user):
    # Tenant mints a token — this logs with the tenant_id.
    client.post("/_twin/tokens", json={
        "app_id": test_app_record["app_id"], "fb_id": test_user["fb_id"],
    }, headers=tenant_headers)

    r_admin = client.get("/_twin/logs", headers=admin_headers)
    assert r_admin.status_code == 200
    assert r_admin.get_json()["logs"], "admin should see logs"

    r_tenant = client.get("/_twin/logs", headers=tenant_headers)
    body = r_tenant.get_json()
    for entry in body["logs"]:
        assert entry.get("tenant_id") == tenant["tenant_id"]


def test_wrong_admin_token_rejected(client, app):
    bad = {"X-Twin-Admin-Token": "wrong"}
    r = client.post("/_twin/apps", json={"redirect_uris": ["https://x/cb"]}, headers=bad)
    assert r.status_code == 401


def test_bearer_admin_token_accepted(client, admin_token):
    r = client.post("/_twin/apps", json={
        "name": "X", "redirect_uris": ["https://x/cb"],
    }, headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 201


def test_cross_tenant_mint_is_rejected(client, tenant_store):
    """Tenant B cannot mint a token for an app owned by tenant A."""
    import base64
    from twins_local.tenants import (
        generate_tenant_id, generate_tenant_secret, hash_secret,
    )

    def _mk(name):
        tid = generate_tenant_id()
        secret = generate_tenant_secret()
        tenant_store.create_tenant(tid, hash_secret(secret), name)
        creds = base64.b64encode(f"{tid}:{secret}".encode()).decode()
        return tid, {"Authorization": f"Basic {creds}"}

    _, headers_a = _mk("A")
    _, headers_b = _mk("B")

    app_a = client.post("/_twin/apps", json={
        "name": "A", "redirect_uris": ["https://a/cb"],
    }, headers=headers_a).get_json()
    user_a = client.post("/_twin/users", json={
        "app_id": app_a["app_id"],
        "name": "Alice A", "email": "alice@a.test", "granted_scopes": ["email"],
    }, headers=headers_a).get_json()

    # Tenant B attempts to mint a token for tenant A's app — must fail at app-scope check.
    r = client.post("/_twin/tokens",
                    json={"app_id": app_a["app_id"], "fb_id": user_a["fb_id"]},
                    headers=headers_b)
    assert r.status_code == 404, "tenant B must not mint tokens for tenant A's app"


def test_cross_tenant_dialog_is_rejected(client, admin_headers):
    """Walking the dialog for app B with twin_user_id=<a's fb_id> must not
    produce a successful redirect — the user doesn't belong to app B."""
    app_a = client.post("/_twin/apps", json={
        "name": "A", "redirect_uris": ["https://a/cb"],
    }, headers=admin_headers).get_json()
    user_a = client.post("/_twin/users", json={
        "app_id": app_a["app_id"],
        "name": "Alice A", "email": "alice@a.test", "granted_scopes": ["email"],
    }, headers=admin_headers).get_json()
    app_b = client.post("/_twin/apps", json={
        "name": "B", "redirect_uris": ["https://b/cb"],
    }, headers=admin_headers).get_json()

    r = client.get("/dialog/oauth", query_string={
        "client_id": app_b["app_id"],
        "redirect_uri": app_b["redirect_uris"][0],
        "response_type": "code",
        "twin_user_id": user_a["fb_id"],
    })
    # No users exist on app_b — twin responds with a 400 "no users configured" page.
    assert r.status_code == 400
    assert b"No test users configured" in r.data


def test_admin_lists_users_scoped_by_app_id(client, admin_headers):
    app_a = client.post("/_twin/apps", json={
        "name": "A", "redirect_uris": ["https://a/cb"],
    }, headers=admin_headers).get_json()
    app_b = client.post("/_twin/apps", json={
        "name": "B", "redirect_uris": ["https://b/cb"],
    }, headers=admin_headers).get_json()
    client.post("/_twin/users", json={"app_id": app_a["app_id"], "name": "Au"},
                headers=admin_headers)
    client.post("/_twin/users", json={"app_id": app_b["app_id"], "name": "Bu"},
                headers=admin_headers)

    r_a = client.get(f"/_twin/users?app_id={app_a['app_id']}", headers=admin_headers)
    r_all = client.get("/_twin/users", headers=admin_headers)
    assert len(r_a.get_json()["users"]) == 1
    assert len(r_all.get_json()["users"]) == 2


def test_settings_toggle_renders_interactive_dialog(client, admin_headers, admin_token, test_app_record, test_user):
    """PUT /_twin/settings + interactive_dialog=true → next dialog GET renders HTML."""
    r = client.put("/_twin/settings", json={"interactive_dialog": True},
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.get_json()["settings"]["interactive_dialog"] is True

    r2 = client.get("/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "response_type": "code",
    })
    assert r2.status_code == 200
    assert b"<form" in r2.data


def test_logs_limit_is_capped(client, admin_headers):
    r = client.get("/_twin/logs?limit=1000000", headers=admin_headers)
    assert r.status_code == 200
    assert r.get_json()["limit"] == 1000

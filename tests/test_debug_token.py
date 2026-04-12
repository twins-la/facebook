"""debug_token: validity, app_id attribution, substitution detection."""


def _mint(client, tenant_headers, app_id, fb_id):
    r = client.post("/_twin/tokens", json={
        "app_id": app_id, "fb_id": fb_id, "scopes": ["email"],
    }, headers=tenant_headers)
    return r.get_json()["access_token"]


def test_debug_valid_user_token(client, basic_auth, test_app_record, test_user, tenant_headers):
    tok = _mint(client, tenant_headers, test_app_record["app_id"], test_user["fb_id"])
    app_token = f"{test_app_record['app_id']}|{test_app_record['app_secret']}"
    r = client.get("/v19.0/debug_token", query_string={
        "input_token": tok, "access_token": app_token,
    })
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["app_id"] == test_app_record["app_id"]
    assert data["user_id"] == test_user["fb_id"]
    assert data["is_valid"] is True
    assert data["type"] == "USER"


def test_debug_revoked_token_is_invalid(client, basic_auth, storage, test_app_record, test_user, tenant_headers):
    tok = _mint(client, tenant_headers, test_app_record["app_id"], test_user["fb_id"])
    storage.revoke_access_token(tok)
    app_token = f"{test_app_record['app_id']}|{test_app_record['app_secret']}"
    r = client.get("/v19.0/debug_token", query_string={
        "input_token": tok, "access_token": app_token,
    })
    assert r.get_json()["data"]["is_valid"] is False


def test_debug_detects_cross_app_token(client, admin_headers, basic_auth, test_app_record, test_user, tenant_headers):
    # Create a second app; issue a token for test_user via app1 (existing).
    tok = _mint(client, tenant_headers, test_app_record["app_id"], test_user["fb_id"])
    r = client.post("/_twin/apps", json={
        "name": "App2", "redirect_uris": ["https://a2/cb"],
    }, headers=admin_headers)
    app2 = r.get_json()
    app2_token = f"{app2['app_id']}|{app2['app_secret']}"
    r2 = client.get("/v19.0/debug_token", query_string={
        "input_token": tok, "access_token": app2_token,
    })
    # input_token's app_id is app1 — not app2. Consumer checks app_id vs.
    # their own app_id to detect substitution.
    data = r2.get_json()["data"]
    assert data["app_id"] == test_app_record["app_id"]
    assert data["app_id"] != app2["app_id"]


def test_debug_missing_input_token(client, test_app_record):
    app_token = f"{test_app_record['app_id']}|{test_app_record['app_secret']}"
    r = client.get("/v19.0/debug_token", query_string={"access_token": app_token})
    assert r.status_code == 400


def test_debug_missing_access_token(client):
    r = client.get("/v19.0/debug_token", query_string={"input_token": "foo"})
    assert r.status_code == 400


def test_debug_unknown_input_token(client, test_app_record):
    app_token = f"{test_app_record['app_id']}|{test_app_record['app_secret']}"
    r = client.get("/v19.0/debug_token", query_string={
        "input_token": "EAAbogus", "access_token": app_token,
    })
    assert r.status_code == 200
    assert r.get_json()["data"]["is_valid"] is False


def test_debug_bad_app_token_rejected(client):
    r = client.get("/v19.0/debug_token", query_string={
        "input_token": "x", "access_token": "123|wrong",
    })
    assert r.status_code == 400
    # Invalid-but-present caller credentials → OAuthException 190
    # (parity with real Facebook; was 100 in an earlier cut).
    assert r.get_json()["error"]["code"] == 190


def test_debug_user_token_as_caller_works(client, basic_auth, test_user, tenant_headers, test_app_record):
    """A valid user access token may authenticate the caller. Exercises the
    non-app-token code path in debug_token that wasn't previously covered."""
    tok = _mint(client, tenant_headers, test_app_record["app_id"], test_user["fb_id"])
    r = client.get("/v19.0/debug_token", query_string={
        "input_token": tok, "access_token": tok,
    })
    assert r.status_code == 200
    assert r.get_json()["data"]["user_id"] == test_user["fb_id"]


def test_debug_unknown_user_caller_token_rejected(client, test_app_record):
    """An unknown user access token as caller → 190, not 100 or 200."""
    r = client.get("/v19.0/debug_token", query_string={
        "input_token": "EAAwhatever", "access_token": "EAAunknown",
    })
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == 190

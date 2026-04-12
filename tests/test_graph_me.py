"""Graph /me: field selection, token passing modes, missing email, invalid/expired tokens."""

import urllib.parse


def _mint(client, basic_auth, fb_id, scopes=None):
    r = client.post("/_twin/tokens", json={
        "fb_id": fb_id, "scopes": scopes or ["email", "public_profile"],
    }, headers=basic_auth)
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["access_token"]


def test_me_default_fields(client, basic_auth, test_user):
    tok = _mint(client, basic_auth, test_user["fb_id"])
    r = client.get("/v19.0/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["id"] == test_user["fb_id"]
    assert body["name"] == "Alice Example"
    assert "email" not in body  # default fields are id,name


def test_me_all_fields_via_bearer(client, basic_auth, test_user):
    tok = _mint(client, basic_auth, test_user["fb_id"])
    r = client.get("/v19.0/me?fields=id,name,email",
                   headers={"Authorization": f"Bearer {tok}"})
    body = r.get_json()
    assert body == {
        "id": test_user["fb_id"],
        "name": "Alice Example",
        "email": "alice@example.com",
    }


def test_me_via_query_access_token(client, basic_auth, test_user):
    tok = _mint(client, basic_auth, test_user["fb_id"])
    r = client.get(f"/v19.0/me?fields=id&access_token={tok}")
    assert r.status_code == 200
    assert r.get_json() == {"id": test_user["fb_id"]}


def test_me_token_precedence_bearer_beats_query(client, basic_auth, test_user):
    """Bearer header takes precedence over ?access_token=, matching the
    extraction order documented in graph_me._extract_token."""
    tok = _mint(client, basic_auth, test_user["fb_id"])
    r = client.get(
        f"/v19.0/me?fields=id&access_token=EAAbogus",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert r.get_json()["id"] == test_user["fb_id"]


def test_me_v21(client, basic_auth, test_user):
    tok = _mint(client, basic_auth, test_user["fb_id"])
    r = client.get("/v21.0/me?fields=id", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200


def test_me_missing_email_scope(client, basic_auth, admin_headers, test_app_record, test_user):
    # Revoke email scope on this user.
    client.patch(
        f"/_twin/apps/{test_app_record['app_id']}/users/{test_user['fb_id']}",
        json={"granted_scopes": ["public_profile"]},
        headers=admin_headers,
    )
    tok = _mint(client, basic_auth, test_user["fb_id"], scopes=["email"])
    r = client.get("/v19.0/me?fields=id,name,email",
                   headers={"Authorization": f"Bearer {tok}"})
    body = r.get_json()
    assert "email" not in body  # missing, not an error


def test_me_invalid_token(client):
    r = client.get("/v19.0/me",
                   headers={"Authorization": "Bearer EAAnotreal"})
    assert r.status_code == 400
    err = r.get_json()["error"]
    assert err["code"] == 190


def test_me_simulated_invalid(client, basic_auth, admin_headers, test_app_record, test_user):
    tok = _mint(client, basic_auth, test_user["fb_id"])
    client.patch(
        f"/_twin/apps/{test_app_record['app_id']}/users/{test_user['fb_id']}",
        json={"simulate_invalid": True},
        headers=admin_headers,
    )
    r = client.get("/v19.0/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == 190


def test_me_simulated_expired(client, basic_auth, admin_headers, test_app_record, test_user):
    tok = _mint(client, basic_auth, test_user["fb_id"])
    client.patch(
        f"/_twin/apps/{test_app_record['app_id']}/users/{test_user['fb_id']}",
        json={"simulate_expired": True},
        headers=admin_headers,
    )
    r = client.get("/v19.0/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400
    err = r.get_json()["error"]
    assert err["code"] == 190
    assert err.get("error_subcode") == 463


def test_me_revoked_token(client, basic_auth, storage, test_user):
    tok = _mint(client, basic_auth, test_user["fb_id"])
    assert storage.revoke_access_token(tok)
    r = client.get("/v19.0/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400
    assert r.get_json()["error"]["error_subcode"] == 467


def test_me_unknown_field_returns_error(client, basic_auth, test_user):
    tok = _mint(client, basic_auth, test_user["fb_id"])
    r = client.get("/v19.0/me?fields=id,shenanigans",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400
    assert "shenanigans" in r.get_json()["error"]["message"]


def test_me_missing_token(client):
    r = client.get("/v19.0/me")
    assert r.status_code == 400


def test_user_by_id_self_ok(client, basic_auth, test_user):
    tok = _mint(client, basic_auth, test_user["fb_id"])
    r = client.get(f"/v19.0/{test_user['fb_id']}?fields=id,name",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.get_json()["id"] == test_user["fb_id"]


def test_user_by_id_other_rejected(client, basic_auth, admin_headers, test_app_record, test_user):
    tok = _mint(client, basic_auth, test_user["fb_id"])
    r2 = client.post("/_twin/users", json={
        "app_id": test_app_record["app_id"],
        "name": "Other", "email": "o@x.com", "granted_scopes": ["email"],
    }, headers=admin_headers)
    other_id = r2.get_json()["fb_id"]
    r = client.get(f"/v19.0/{other_id}?fields=id,name",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400

"""Full end-to-end flow using only the Flask test client as HTTP transport.

Walks: create app → create user → dialog → token exchange → /me → debug_token.
This is the "consumer's code works with only a URL swap" smoke test.
"""

import urllib.parse


def test_end_to_end_code_flow(client, admin_headers):
    # 1. Twin setup: create app and user via Twin Plane.
    app = client.post("/_twin/apps", json={
        "name": "Smoke App",
        "redirect_uris": ["https://client.example/oauth/callback"],
    }, headers=admin_headers).get_json()
    user = client.post("/_twin/users", json={
        "app_id": app["app_id"],
        "name": "Carol Smith",
        "email": "carol@example.com",
        "granted_scopes": ["email", "public_profile"],
    }, headers=admin_headers).get_json()

    # 2. Dialog: consumer redirects user here.
    r = client.get("/v19.0/dialog/oauth", query_string={
        "client_id": app["app_id"],
        "redirect_uri": app["redirect_uris"][0],
        "response_type": "code",
        "state": "csrf-state-xyz",
        "scope": "email,public_profile",
    })
    assert r.status_code == 302
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r.headers["Location"]).query))
    assert q["state"] == "csrf-state-xyz"
    code = q["code"]

    # 3. Token exchange: consumer's backend.
    r = client.get("/v19.0/oauth/access_token", query_string={
        "client_id": app["app_id"],
        "client_secret": app["app_secret"],
        "redirect_uri": app["redirect_uris"][0],
        "code": code,
    })
    assert r.status_code == 200
    token = r.get_json()["access_token"]

    # 4. /me: fetch identity.
    r = client.get("/v19.0/me?fields=id,name,email",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.get_json()
    assert body == {
        "id": user["fb_id"],
        "name": "Carol Smith",
        "email": "carol@example.com",
    }

    # 5. debug_token: validate app attribution.
    app_token = f"{app['app_id']}|{app['app_secret']}"
    r = client.get("/v19.0/debug_token", query_string={
        "input_token": token, "access_token": app_token,
    })
    data = r.get_json()["data"]
    assert data["app_id"] == app["app_id"]
    assert data["user_id"] == user["fb_id"]
    assert data["is_valid"] is True

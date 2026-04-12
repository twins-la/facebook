"""End-to-end smoke test using the `requests` library against a live server.

This is the real "URL swap and your code works" test. It boots the twin on
a real socket, then walks OAuth with plain `requests` — no Flask test
client, no in-process shortcuts. If anything about the wire format,
redirect handling, or header semantics differs from a real HTTP client,
this test catches it.
"""

import threading
import urllib.parse

import pytest
import requests
from werkzeug.serving import make_server


@pytest.fixture
def live_server(app):
    """Boot the Flask app on a random local port; tear it down after."""
    server = make_server("127.0.0.1", 0, app)
    host, port = server.server_address[0], server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_end_to_end_with_requests(live_server, admin_token):
    base = live_server
    headers = {"X-Twin-Admin-Token": admin_token}

    app = requests.post(f"{base}/_twin/apps", json={
        "name": "HTTP Smoke App",
        "redirect_uris": ["https://client.example/oauth/callback"],
    }, headers=headers).json()
    user = requests.post(f"{base}/_twin/users", json={
        "app_id": app["app_id"],
        "name": "Dan Test", "email": "dan@example.com",
        "granted_scopes": ["email", "public_profile"],
    }, headers=headers).json()

    # Dialog — real redirect, real 302, real Location header.
    r = requests.get(f"{base}/v19.0/dialog/oauth", params={
        "client_id": app["app_id"],
        "redirect_uri": app["redirect_uris"][0],
        "response_type": "code",
        "state": "csrf-xyz",
    }, allow_redirects=False)
    assert r.status_code == 302
    loc = urllib.parse.urlparse(r.headers["Location"])
    q = dict(urllib.parse.parse_qsl(loc.query))
    assert q["state"] == "csrf-xyz"
    code = q["code"]

    # Token exchange.
    r = requests.get(f"{base}/v19.0/oauth/access_token", params={
        "client_id": app["app_id"],
        "client_secret": app["app_secret"],
        "redirect_uri": app["redirect_uris"][0],
        "code": code,
    })
    assert r.status_code == 200
    token = r.json()["access_token"]

    # /me via Bearer.
    r = requests.get(f"{base}/v19.0/me",
                     params={"fields": "id,name,email"},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body == {"id": user["fb_id"], "name": "Dan Test",
                    "email": "dan@example.com"}

    # /me via form-body POST — not what real Facebook supports (they use GET),
    # but exercises the form-extraction path on the twin. Skipped — /me is
    # GET-only and this isn't a real-Facebook scenario.

    # /debug_token.
    app_token = f"{app['app_id']}|{app['app_secret']}"
    r = requests.get(f"{base}/v19.0/debug_token",
                     params={"input_token": token, "access_token": app_token})
    data = r.json()["data"]
    assert data["app_id"] == app["app_id"]
    assert data["user_id"] == user["fb_id"]
    assert data["is_valid"] is True

"""OAuth token exchange: happy path, reuse, expiry, wrong secret, redirect mismatch."""

import time
import urllib.parse


def _get_code(client, app_record, user, redirect_uri=None):
    redirect_uri = redirect_uri or app_record["redirect_uris"][0]
    r = client.get("/dialog/oauth", query_string={
        "client_id": app_record["app_id"],
        "redirect_uri": redirect_uri,
        "state": "s",
        "response_type": "code",
    })
    assert r.status_code == 302
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r.headers["Location"]).query))
    return q["code"]


def test_exchange_happy_path(client, test_app_record, test_user):
    code = _get_code(client, test_app_record, test_user)
    r = client.get("/v19.0/oauth/access_token", query_string={
        "client_id": test_app_record["app_id"],
        "client_secret": test_app_record["app_secret"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "code": code,
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["access_token"].startswith("EAA")
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_exchange_works_on_v21(client, test_app_record, test_user):
    code = _get_code(client, test_app_record, test_user)
    r = client.get("/v21.0/oauth/access_token", query_string={
        "client_id": test_app_record["app_id"],
        "client_secret": test_app_record["app_secret"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "code": code,
    })
    assert r.status_code == 200


def test_code_reuse_rejected(client, test_app_record, test_user):
    code = _get_code(client, test_app_record, test_user)
    params = {
        "client_id": test_app_record["app_id"],
        "client_secret": test_app_record["app_secret"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "code": code,
    }
    r1 = client.get("/v19.0/oauth/access_token", query_string=params)
    assert r1.status_code == 200
    r2 = client.get("/v19.0/oauth/access_token", query_string=params)
    assert r2.status_code == 400
    assert r2.get_json()["error"]["code"] == 100


def test_wrong_secret_rejected(client, test_app_record, test_user):
    code = _get_code(client, test_app_record, test_user)
    r = client.get("/v19.0/oauth/access_token", query_string={
        "client_id": test_app_record["app_id"],
        "client_secret": "0" * 32,
        "redirect_uri": test_app_record["redirect_uris"][0],
        "code": code,
    })
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == 101


def test_redirect_uri_mismatch_rejected(client, admin_headers, test_app_record, test_user):
    # Add a second registered URI so both are valid per-app, but they differ
    # between dialog time and token exchange time.
    client.post("/_twin/apps", json={
        "name": "Demo2",
        "redirect_uris": [test_app_record["redirect_uris"][0], "https://other/cb"],
    }, headers=admin_headers)
    code = _get_code(client, test_app_record, test_user, redirect_uri=test_app_record["redirect_uris"][0])
    r = client.get("/v19.0/oauth/access_token", query_string={
        "client_id": test_app_record["app_id"],
        "client_secret": test_app_record["app_secret"],
        "redirect_uri": "https://other/cb",  # different from the one used for the code
        "code": code,
    })
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == 191


def test_missing_params(client, test_app_record):
    r = client.get("/v19.0/oauth/access_token", query_string={})
    assert r.status_code == 400


def test_app_access_token_via_client_credentials(client, test_app_record):
    r = client.get("/v19.0/oauth/access_token", query_string={
        "client_id": test_app_record["app_id"],
        "client_secret": test_app_record["app_secret"],
        "grant_type": "client_credentials",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["access_token"] == f"{test_app_record['app_id']}|{test_app_record['app_secret']}"


def test_expired_authorization_code_rejected(client, storage, test_app_record, test_user):
    """Direct-create an auth code in the past to exercise the expiry branch."""
    import time
    now = int(time.time())
    storage.create_auth_code({
        "code": "AQ-expired",
        "app_id": test_app_record["app_id"],
        "user_fb_id": test_user["fb_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "scopes": ["email"],
        "expires_at": now - 1,
        "consumed": False,
    })
    r = client.get("/v19.0/oauth/access_token", query_string={
        "client_id": test_app_record["app_id"],
        "client_secret": test_app_record["app_secret"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "code": "AQ-expired",
    })
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == 100


def test_unsupported_version(client, test_app_record):
    r = client.get("/v10.0/oauth/access_token", query_string={
        "client_id": test_app_record["app_id"],
        "client_secret": test_app_record["app_secret"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "code": "x",
    })
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == 2500

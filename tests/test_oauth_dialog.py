"""OAuth dialog: code + implicit flows, denial, redirect URI validation."""

import urllib.parse


def _parse_location(resp):
    loc = resp.headers["Location"]
    parsed = urllib.parse.urlparse(loc)
    query = dict(urllib.parse.parse_qsl(parsed.query))
    frag = dict(urllib.parse.parse_qsl(parsed.fragment))
    return parsed, query, frag


def test_code_flow_happy_path(client, test_app_record, test_user):
    r = client.get("/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "state": "xyz",
        "response_type": "code",
        "scope": "email,public_profile",
    })
    assert r.status_code == 302
    parsed, query, _ = _parse_location(r)
    assert parsed.netloc == "client.example"
    assert "code" in query
    assert query["state"] == "xyz"


def test_implicit_flow_returns_token_in_fragment(client, test_app_record, test_user):
    r = client.get("/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "state": "s1",
        "response_type": "token",
        "scope": "email",
    })
    assert r.status_code == 302
    _, _, frag = _parse_location(r)
    assert frag["access_token"].startswith("EAA")
    assert frag["token_type"] == "bearer"
    assert frag["state"] == "s1"
    assert int(frag["expires_in"]) > 0


def test_denial_simulation_code_flow(client, test_app_record, test_user):
    r = client.get("/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "state": "s2",
        "response_type": "code",
        "twin_simulate": "denied",
    })
    assert r.status_code == 302
    _, query, _ = _parse_location(r)
    assert query["error"] == "access_denied"
    assert query["state"] == "s2"


def test_denial_simulation_implicit_flow(client, test_app_record, test_user):
    r = client.get("/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "state": "s3",
        "response_type": "token",
        "twin_simulate": "denied",
    })
    assert r.status_code == 302
    _, _, frag = _parse_location(r)
    assert frag["error"] == "access_denied"
    assert frag["state"] == "s3"


def test_unregistered_redirect_uri_rejected(client, test_app_record, test_user):
    r = client.get("/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": "https://evil.example/cb",
        "response_type": "code",
    })
    assert r.status_code == 400
    assert b"not registered" in r.data


def test_unknown_app_rejected(client, test_user):
    r = client.get("/dialog/oauth", query_string={
        "client_id": "000000000000",
        "redirect_uri": "https://any/cb",
        "response_type": "code",
    })
    assert r.status_code == 400


def test_unsupported_response_type_rejected(client, test_app_record, test_user):
    r = client.get("/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "response_type": "password",
    })
    assert r.status_code == 400


def test_error_page_escapes_reflected_response_type(client, test_app_record, test_user):
    """The error page reflects `response_type` back in its body. Ensure HTML
    entities are escaped so this isn't a reflected XSS sink."""
    r = client.get("/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "response_type": "<script>alert(1)</script>",
    })
    assert r.status_code == 400
    assert b"<script>alert(1)</script>" not in r.data
    assert b"&lt;script&gt;" in r.data


def test_versioned_dialog_path(client, test_app_record, test_user):
    r = client.get("/v19.0/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "response_type": "code",
    })
    assert r.status_code == 302


def test_unknown_version_in_dialog(client, test_app_record, test_user):
    r = client.get("/v99.0/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "response_type": "code",
    })
    assert r.status_code == 400


def test_multiple_users_renders_picker(client, admin_headers, test_app_record):
    # Two users → dialog should render HTML picker when no twin_user_id.
    for i in range(2):
        client.post("/_twin/users", json={
            "app_id": test_app_record["app_id"],
            "name": f"User {i}", "email": f"u{i}@x.com",
            "granted_scopes": ["email"],
        }, headers=admin_headers)

    r = client.get("/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "response_type": "code",
    })
    assert r.status_code == 200
    assert b"<form" in r.data


def test_twin_user_id_picks_specific_user(client, admin_headers, test_app_record):
    ids = []
    for i in range(2):
        r = client.post("/_twin/users", json={
            "app_id": test_app_record["app_id"],
            "name": f"User {i}", "email": f"u{i}@x.com",
            "granted_scopes": ["email"],
        }, headers=admin_headers)
        ids.append(r.get_json()["fb_id"])

    r = client.get("/dialog/oauth", query_string={
        "client_id": test_app_record["app_id"],
        "redirect_uri": test_app_record["redirect_uris"][0],
        "response_type": "code",
        "twin_user_id": ids[1],
    })
    assert r.status_code == 302

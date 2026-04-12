"""Every supported Graph API version routes correctly; unknown versions 400."""

import pytest

from twins_facebook.versions import SUPPORTED_VERSIONS


def _mint(client, tenant_headers, app_id, fb_id):
    r = client.post("/_twin/tokens", json={
        "app_id": app_id, "fb_id": fb_id,
    }, headers=tenant_headers)
    return r.get_json()["access_token"]


@pytest.mark.parametrize("version", SUPPORTED_VERSIONS)
def test_me_routes_on_every_supported_version(client, basic_auth, test_user, version, tenant_headers, test_app_record):
    tok = _mint(client, tenant_headers, test_app_record["app_id"], test_user["fb_id"])
    r = client.get(f"/{version}/me?fields=id",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200


@pytest.mark.parametrize("version", SUPPORTED_VERSIONS)
def test_debug_token_routes_on_every_supported_version(client, basic_auth, test_app_record, test_user, version, tenant_headers):
    tok = _mint(client, tenant_headers, test_app_record["app_id"], test_user["fb_id"])
    app_token = f"{test_app_record['app_id']}|{test_app_record['app_secret']}"
    r = client.get(f"/{version}/debug_token", query_string={
        "input_token": tok, "access_token": app_token,
    })
    assert r.status_code == 200


def test_unknown_version_on_me(client):
    r = client.get("/v50.0/me", headers={"Authorization": "Bearer x"})
    assert r.status_code == 400


def test_unknown_version_on_access_token(client):
    r = client.get("/v50.0/oauth/access_token")
    assert r.status_code == 400


def test_unknown_version_on_debug_token(client):
    r = client.get("/v50.0/debug_token")
    assert r.status_code == 400


def test_404_on_unknown_api_path(client):
    r = client.get("/v19.0/something/unknown")
    # path that starts with /v -> JSON error envelope
    assert r.status_code == 404
    assert r.get_json()["error"]["type"] == "GraphMethodException"


def test_404_on_non_api_path(client):
    r = client.get("/totally-unknown")
    assert r.status_code == 404

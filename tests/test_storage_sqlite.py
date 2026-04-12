"""Tests for the local SQLite FacebookTwinStorage implementation.

Verifies that the local host's SQLite implementation conforms to the
FacebookTwinStorage ABC, independent of the package-level tests that
use an in-memory stub.
"""

import os
import sys
import time

import pytest

# twins_facebook_local is a sibling package under this repo; make it importable.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from twins_facebook_local.storage_sqlite import SQLiteFacebookStorage


@pytest.fixture
def storage(tmp_path):
    return SQLiteFacebookStorage(db_path=str(tmp_path / "fb.db"))


def _app_data(app_id="100000000000001", tenant_id="tnt-test"):
    now = int(time.time())
    return {
        "app_id": app_id, "tenant_id": tenant_id, "app_secret": "s" * 32,
        "name": "App", "redirect_uris": ["https://c/cb"],
        "date_created": now, "date_updated": now,
    }


def _user_data(fb_id="1000000000000001", app_id="100000000000001",
               tenant_id="tnt-test"):
    now = int(time.time())
    return {
        "app_id": app_id, "tenant_id": tenant_id, "fb_id": fb_id,
        "name": "Alice", "email": "a@x.com",
        "granted_scopes": ["email"],
        "simulate_invalid": False, "simulate_expired": False,
        "date_created": now, "date_updated": now,
    }


def test_app_lifecycle(storage):
    a = storage.create_app_record(_app_data())
    assert a["app_id"] == "100000000000001"
    assert a["redirect_uris"] == ["https://c/cb"]
    assert storage.get_app("100000000000001")["app_secret"] == "s" * 32
    assert len(storage.list_apps()) == 1
    assert storage.delete_app("100000000000001") is True
    assert storage.get_app("100000000000001") is None
    assert storage.delete_app("nonexistent") is False


def test_user_lifecycle_and_update(storage):
    storage.create_app_record(_app_data())
    storage.create_user(_user_data())
    assert storage.get_user("100000000000001", "1000000000000001")["email"] == "a@x.com"
    updated = storage.update_user("100000000000001", "1000000000000001",
                                  {"granted_scopes": ["public_profile"]})
    assert "email" not in updated["granted_scopes"]
    assert storage.update_user("100000000000001", "missing", {"name": "X"}) is None
    assert storage.delete_user("100000000000001", "1000000000000001") is True
    assert storage.delete_user("100000000000001", "1000000000000001") is False


def test_user_cross_app_isolation(storage):
    """Same fb_id under two different apps must not collide; fetching by
    (app_A, fb_id) must not return app_B's user."""
    storage.create_app_record(_app_data("APP_A"))
    storage.create_app_record(_app_data("APP_B"))
    storage.create_user({**_user_data(app_id="APP_A"), "email": "a@a"})
    storage.create_user({**_user_data(app_id="APP_B"), "email": "b@b"})
    ua = storage.get_user("APP_A", "1000000000000001")
    ub = storage.get_user("APP_B", "1000000000000001")
    assert ua["email"] == "a@a"
    assert ub["email"] == "b@b"
    assert storage.get_user("APP_A", "nonexistent") is None
    assert storage.get_user("OTHER_APP", "1000000000000001") is None


def test_auth_code_one_shot(storage):
    storage.create_app_record(_app_data())
    storage.create_user(_user_data(app_id="100000000000001"))
    now = int(time.time())
    storage.create_auth_code({
        "code": "AQ1", "app_id": "100000000000001",
        "user_fb_id": "1000000000000001", "redirect_uri": "https://c/cb",
        "scopes": ["email"], "expires_at": now + 600,
    })
    first = storage.consume_auth_code("AQ1")
    assert first is not None
    assert first["user_fb_id"] == "1000000000000001"
    assert storage.consume_auth_code("AQ1") is None  # one-shot


def test_access_token_revocation(storage):
    storage.create_app_record(_app_data())
    storage.create_user(_user_data(app_id="100000000000001"))
    now = int(time.time())
    storage.create_access_token({
        "token": "EAA-t1", "app_id": "100000000000001",
        "user_fb_id": "1000000000000001", "scopes": ["email"],
        "issued_at": now, "expires_at": now + 3600, "is_revoked": False,
    })
    assert storage.get_access_token("EAA-t1")["is_revoked"] is False
    assert storage.revoke_access_token("EAA-t1") is True
    assert storage.get_access_token("EAA-t1")["is_revoked"] is True
    assert storage.revoke_access_token("EAA-missing") is False


def test_list_tokens_scoped(storage):
    storage.create_app_record(_app_data("A1"))
    storage.create_app_record(_app_data("A2"))
    storage.create_user(_user_data(app_id="A1"))
    now = int(time.time())
    for i, app_id in enumerate(("A1", "A2", "A1")):
        storage.create_access_token({
            "token": f"EAA-{i}", "app_id": app_id,
            "user_fb_id": "1000000000000001", "scopes": [],
            "issued_at": now + i, "expires_at": now + 3600,
            "is_revoked": False,
        })
    assert len(storage.list_tokens()) == 3
    assert len(storage.list_tokens("A1")) == 2
    assert len(storage.list_tokens("A2")) == 1


def test_delete_app_cascades(storage):
    storage.create_app_record(_app_data("A1"))
    storage.create_user(_user_data(app_id="A1"))
    now = int(time.time())
    storage.create_auth_code({
        "code": "AQ1", "app_id": "A1",
        "user_fb_id": "1000000000000001", "redirect_uri": "https://c/cb",
        "scopes": [], "expires_at": now + 600,
    })
    storage.create_access_token({
        "token": "EAA-1", "app_id": "A1",
        "user_fb_id": "1000000000000001", "scopes": [],
        "issued_at": now, "expires_at": now + 3600, "is_revoked": False,
    })
    assert storage.delete_app("A1") is True
    assert storage.consume_auth_code("AQ1") is None
    assert storage.get_access_token("EAA-1") is None
    assert storage.get_user("A1", "1000000000000001") is None


def test_logs_scope(storage):
    storage.append_log({"operation": "o1", "tenant_id": "T1", "x": 1})
    storage.append_log({"operation": "o2", "tenant_id": "T2"})
    storage.append_log({"operation": "o3"})  # no tenant_id
    all_logs = storage.list_logs(limit=10)
    assert len(all_logs) == 3
    t1_logs = storage.list_logs(limit=10, tenant_id="T1")
    assert len(t1_logs) == 1
    assert t1_logs[0]["operation"] == "o1"


def test_persistence_across_instances(tmp_path):
    p = str(tmp_path / "persist.db")
    s1 = SQLiteFacebookStorage(db_path=p)
    s1.create_app_record(_app_data("P1"))
    s2 = SQLiteFacebookStorage(db_path=p)
    assert s2.get_app("P1") is not None

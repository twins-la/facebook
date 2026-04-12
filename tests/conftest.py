"""Shared pytest fixtures for the Facebook twin package.

Provides an in-memory FacebookTwinStorage implementation — used ONLY for
package tests, never shipped as a host. Hosts implement the ABC
themselves (SQLite for local, Postgres for cloud).
"""

import base64
import copy
import os
import sys
import threading
from typing import Optional

import pytest

from twins_facebook.app import create_app
from twins_facebook.storage import FacebookTwinStorage
from twins_facebook.ids import generate_fbtrace_id  # noqa: F401 (sanity import)

# Make twins_local importable even when tests run without site-packages install.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "local"))

from twins_local.tenants import (
    SQLiteTenantStore,
    ensure_default_tenant,
    generate_tenant_id,
    generate_tenant_secret,
    hash_secret,
)


class InMemoryStorage(FacebookTwinStorage):
    def __init__(self):
        self._lock = threading.Lock()
        self._apps: dict[str, dict] = {}
        self._users: dict[tuple, dict] = {}
        self._codes: dict[str, dict] = {}
        self._tokens: dict[str, dict] = {}
        self._logs: list[dict] = []

    # apps
    def create_app_record(self, data: dict) -> dict:
        with self._lock:
            self._apps[data["app_id"]] = copy.deepcopy(data)
            return copy.deepcopy(self._apps[data["app_id"]])

    def get_app(self, app_id: str) -> Optional[dict]:
        with self._lock:
            a = self._apps.get(app_id)
            return copy.deepcopy(a) if a else None

    def list_apps(self, tenant_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            if tenant_id is None:
                return [copy.deepcopy(a) for a in self._apps.values()]
            return [copy.deepcopy(a) for a in self._apps.values()
                    if a.get("tenant_id") == tenant_id]

    def delete_app(self, app_id: str) -> bool:
        with self._lock:
            if app_id not in self._apps:
                return False
            del self._apps[app_id]
            for k in [k for k in self._users if k[0] == app_id]:
                del self._users[k]
            for c in list(self._codes):
                if self._codes[c]["app_id"] == app_id:
                    del self._codes[c]
            for t in list(self._tokens):
                if self._tokens[t]["app_id"] == app_id:
                    del self._tokens[t]
            return True

    # users — keyed by (app_id, fb_id) composite
    def create_user(self, data: dict) -> dict:
        key = (data["app_id"], data["fb_id"])
        with self._lock:
            self._users[key] = copy.deepcopy(data)
            return copy.deepcopy(self._users[key])

    def get_user(self, app_id: str, fb_id: str) -> Optional[dict]:
        with self._lock:
            u = self._users.get((app_id, fb_id))
            return copy.deepcopy(u) if u else None

    def list_users(self, app_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            if app_id is None:
                return [copy.deepcopy(u) for u in self._users.values()]
            return [copy.deepcopy(u) for (a, _), u in self._users.items() if a == app_id]

    def update_user(self, app_id: str, fb_id: str, updates: dict) -> Optional[dict]:
        with self._lock:
            u = self._users.get((app_id, fb_id))
            if not u:
                return None
            u.update(copy.deepcopy(updates))
            return copy.deepcopy(u)

    def delete_user(self, app_id: str, fb_id: str) -> bool:
        with self._lock:
            return self._users.pop((app_id, fb_id), None) is not None

    # codes
    def create_auth_code(self, data: dict) -> dict:
        with self._lock:
            self._codes[data["code"]] = copy.deepcopy(data)
            return copy.deepcopy(self._codes[data["code"]])

    def consume_auth_code(self, code: str) -> Optional[dict]:
        with self._lock:
            rec = self._codes.get(code)
            if not rec or rec.get("consumed"):
                return None
            rec["consumed"] = True
            return copy.deepcopy(rec)

    # tokens
    def create_access_token(self, data: dict) -> dict:
        with self._lock:
            self._tokens[data["token"]] = copy.deepcopy(data)
            return copy.deepcopy(self._tokens[data["token"]])

    def get_access_token(self, token: str) -> Optional[dict]:
        with self._lock:
            t = self._tokens.get(token)
            return copy.deepcopy(t) if t else None

    def revoke_access_token(self, token: str) -> bool:
        with self._lock:
            t = self._tokens.get(token)
            if not t:
                return False
            t["is_revoked"] = True
            return True

    def list_tokens(self, app_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            return [
                copy.deepcopy(t) for t in self._tokens.values()
                if app_id is None or t["app_id"] == app_id
            ]

    # logs
    def append_log(self, entry: dict) -> None:
        import time as _t
        e = copy.deepcopy(entry)
        e.setdefault("ts", _t.time())
        with self._lock:
            self._logs.append(e)

    def list_logs(self, limit=100, offset=0, tenant_id=None) -> list[dict]:
        with self._lock:
            src = [l for l in self._logs if tenant_id is None or l.get("tenant_id") == tenant_id]
            src = list(reversed(src))
            return [copy.deepcopy(l) for l in src[offset:offset + limit]]


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def admin_token() -> str:
    return "test-admin-token"


@pytest.fixture
def tenant_store(tmp_path):
    s = SQLiteTenantStore(db_path=str(tmp_path / "tenants.sqlite3"))
    ensure_default_tenant(s)
    return s


@pytest.fixture
def tenant(tenant_store):
    tid = generate_tenant_id()
    secret = generate_tenant_secret()
    tenant_store.create_tenant(tid, hash_secret(secret), "Test Tenant")
    return {"tenant_id": tid, "tenant_secret": secret}


@pytest.fixture
def tenant_headers(tenant):
    creds = base64.b64encode(
        f"{tenant['tenant_id']}:{tenant['tenant_secret']}".encode()
    ).decode()
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def app(storage, admin_token, tenant_store):
    a = create_app(storage=storage, tenants=tenant_store, config={
        "base_url": "http://twin.test",
        "admin_token": admin_token,
    })
    a.testing = True
    return a


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_headers(admin_token):
    return {"X-Twin-Admin-Token": admin_token}


@pytest.fixture
def test_app_record(client, tenant_headers):
    """Create an app via Twin Plane under the test tenant; return full record."""
    resp = client.post("/_twin/apps", json={
        "name": "Test App",
        "redirect_uris": ["https://client.example/callback"],
    }, headers=tenant_headers)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


@pytest.fixture
def test_user(client, tenant_headers, test_app_record):
    resp = client.post("/_twin/users", json={
        "app_id": test_app_record["app_id"],
        "name": "Alice Example",
        "email": "alice@example.com",
        "granted_scopes": ["email", "public_profile"],
    }, headers=tenant_headers)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


@pytest.fixture
def basic_auth(test_app_record):
    """Resource-level Basic Auth (app_id:app_secret) for the Graph/OAuth surface."""
    creds = f"{test_app_record['app_id']}:{test_app_record['app_secret']}"
    return {"Authorization": "Basic " + base64.b64encode(creds.encode()).decode()}

"""SQLite implementation of FacebookTwinStorage.

Persists apps, users, auth codes, access tokens, and logs for the
local-hosted Facebook twin. List-valued fields (redirect_uris, scopes)
are JSON-encoded in TEXT columns.
"""

import json
import sqlite3
import threading
from typing import Optional

from twins_facebook.storage import FacebookTwinStorage


class SQLiteFacebookStorage(FacebookTwinStorage):
    """SQLite-backed storage for the Facebook twin.

    Thread-safe via a per-instance lock. Uses WAL mode for concurrent reads.
    """

    def __init__(self, db_path: str = "data/facebook.db"):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def _init_db(self):
        with self._lock:
            c = self._conn()
            try:
                c.executescript("""
                    CREATE TABLE IF NOT EXISTS apps (
                        app_id TEXT PRIMARY KEY,
                        app_secret TEXT NOT NULL,
                        name TEXT NOT NULL DEFAULT '',
                        redirect_uris TEXT NOT NULL DEFAULT '[]',
                        date_created INTEGER NOT NULL,
                        date_updated INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS users (
                        app_id TEXT NOT NULL,
                        fb_id TEXT NOT NULL,
                        name TEXT NOT NULL DEFAULT '',
                        email TEXT NOT NULL DEFAULT '',
                        granted_scopes TEXT NOT NULL DEFAULT '[]',
                        simulate_invalid INTEGER NOT NULL DEFAULT 0,
                        simulate_expired INTEGER NOT NULL DEFAULT 0,
                        date_created INTEGER NOT NULL,
                        date_updated INTEGER NOT NULL,
                        PRIMARY KEY (app_id, fb_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_users_app ON users(app_id);
                    CREATE TABLE IF NOT EXISTS auth_codes (
                        code TEXT PRIMARY KEY,
                        app_id TEXT NOT NULL,
                        user_fb_id TEXT NOT NULL,
                        redirect_uri TEXT NOT NULL,
                        scopes TEXT NOT NULL DEFAULT '[]',
                        expires_at INTEGER NOT NULL,
                        consumed INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS access_tokens (
                        token TEXT PRIMARY KEY,
                        app_id TEXT NOT NULL,
                        user_fb_id TEXT NOT NULL,
                        scopes TEXT NOT NULL DEFAULT '[]',
                        issued_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL,
                        is_revoked INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE INDEX IF NOT EXISTS idx_tokens_app ON access_tokens(app_id);
                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts REAL NOT NULL,
                        app_id TEXT NOT NULL DEFAULT '',
                        entry TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_logs_app ON logs(app_id);
                """)
                c.commit()
            finally:
                c.close()

    # -- apps --

    def create_app_record(self, data: dict) -> dict:
        with self._lock:
            c = self._conn()
            try:
                c.execute(
                    "INSERT INTO apps (app_id, app_secret, name, redirect_uris,"
                    " date_created, date_updated) VALUES (?, ?, ?, ?, ?, ?)",
                    (data["app_id"], data["app_secret"], data.get("name", ""),
                     json.dumps(list(data.get("redirect_uris", []))),
                     data["date_created"], data["date_updated"]),
                )
                c.commit()
            finally:
                c.close()
        return self.get_app(data["app_id"])  # type: ignore[return-value]

    def get_app(self, app_id: str) -> Optional[dict]:
        with self._lock:
            c = self._conn()
            try:
                row = c.execute("SELECT * FROM apps WHERE app_id = ?", (app_id,)).fetchone()
            finally:
                c.close()
        return _app_row(row) if row else None

    def list_apps(self) -> list[dict]:
        with self._lock:
            c = self._conn()
            try:
                rows = c.execute("SELECT * FROM apps ORDER BY date_created").fetchall()
            finally:
                c.close()
        return [_app_row(r) for r in rows]

    def delete_app(self, app_id: str) -> bool:
        with self._lock:
            c = self._conn()
            try:
                cur = c.execute("DELETE FROM apps WHERE app_id = ?", (app_id,))
                existed = cur.rowcount > 0
                c.execute("DELETE FROM users WHERE app_id = ?", (app_id,))
                c.execute("DELETE FROM auth_codes WHERE app_id = ?", (app_id,))
                c.execute("DELETE FROM access_tokens WHERE app_id = ?", (app_id,))
                c.commit()
                return existed
            finally:
                c.close()

    # -- users (per-app scoped) --

    def create_user(self, data: dict) -> dict:
        with self._lock:
            c = self._conn()
            try:
                c.execute(
                    "INSERT INTO users (app_id, fb_id, name, email, granted_scopes,"
                    " simulate_invalid, simulate_expired, date_created, date_updated)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (data["app_id"], data["fb_id"], data.get("name", ""),
                     data.get("email", ""),
                     json.dumps(list(data.get("granted_scopes", []))),
                     1 if data.get("simulate_invalid") else 0,
                     1 if data.get("simulate_expired") else 0,
                     data["date_created"], data["date_updated"]),
                )
                c.commit()
            finally:
                c.close()
        return self.get_user(data["app_id"], data["fb_id"])  # type: ignore[return-value]

    def get_user(self, app_id: str, fb_id: str) -> Optional[dict]:
        with self._lock:
            c = self._conn()
            try:
                row = c.execute(
                    "SELECT * FROM users WHERE app_id = ? AND fb_id = ?",
                    (app_id, fb_id),
                ).fetchone()
            finally:
                c.close()
        return _user_row(row) if row else None

    def list_users(self, app_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            c = self._conn()
            try:
                if app_id is None:
                    rows = c.execute("SELECT * FROM users ORDER BY date_created").fetchall()
                else:
                    rows = c.execute(
                        "SELECT * FROM users WHERE app_id = ? ORDER BY date_created",
                        (app_id,),
                    ).fetchall()
            finally:
                c.close()
        return [_user_row(r) for r in rows]

    def update_user(self, app_id: str, fb_id: str, updates: dict) -> Optional[dict]:
        allowed = {"name", "email", "granted_scopes", "simulate_invalid",
                   "simulate_expired", "date_updated"}
        clauses, params = [], []
        for k, v in updates.items():
            if k not in allowed:
                continue
            if k == "granted_scopes":
                v = json.dumps(list(v))
            if k in ("simulate_invalid", "simulate_expired"):
                v = 1 if v else 0
            clauses.append(f"{k} = ?")
            params.append(v)
        if not clauses:
            return self.get_user(app_id, fb_id)
        params.extend([app_id, fb_id])
        with self._lock:
            c = self._conn()
            try:
                cur = c.execute(
                    f"UPDATE users SET {', '.join(clauses)} WHERE app_id = ? AND fb_id = ?",
                    params,
                )
                c.commit()
                if cur.rowcount == 0:
                    return None
            finally:
                c.close()
        return self.get_user(app_id, fb_id)

    def delete_user(self, app_id: str, fb_id: str) -> bool:
        with self._lock:
            c = self._conn()
            try:
                cur = c.execute(
                    "DELETE FROM users WHERE app_id = ? AND fb_id = ?",
                    (app_id, fb_id),
                )
                c.commit()
                return cur.rowcount > 0
            finally:
                c.close()

    # -- codes --

    def create_auth_code(self, data: dict) -> dict:
        with self._lock:
            c = self._conn()
            try:
                c.execute(
                    "INSERT INTO auth_codes (code, app_id, user_fb_id,"
                    " redirect_uri, scopes, expires_at, consumed)"
                    " VALUES (?, ?, ?, ?, ?, ?, 0)",
                    (data["code"], data["app_id"], data["user_fb_id"],
                     data["redirect_uri"],
                     json.dumps(list(data.get("scopes", []))),
                     int(data["expires_at"])),
                )
                c.commit()
            finally:
                c.close()
        return {**data, "consumed": False}

    def consume_auth_code(self, code: str) -> Optional[dict]:
        with self._lock:
            c = self._conn()
            try:
                c.execute("BEGIN IMMEDIATE")
                row = c.execute(
                    "SELECT * FROM auth_codes WHERE code = ? AND consumed = 0",
                    (code,),
                ).fetchone()
                if not row:
                    c.commit()
                    return None
                c.execute("UPDATE auth_codes SET consumed = 1 WHERE code = ?", (code,))
                c.commit()
            finally:
                c.close()
        return _code_row(row)

    # -- tokens --

    def create_access_token(self, data: dict) -> dict:
        with self._lock:
            c = self._conn()
            try:
                c.execute(
                    "INSERT INTO access_tokens (token, app_id, user_fb_id,"
                    " scopes, issued_at, expires_at, is_revoked)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (data["token"], data["app_id"], data["user_fb_id"],
                     json.dumps(list(data.get("scopes", []))),
                     int(data["issued_at"]), int(data["expires_at"]),
                     1 if data.get("is_revoked") else 0),
                )
                c.commit()
            finally:
                c.close()
        return dict(data)

    def get_access_token(self, token: str) -> Optional[dict]:
        with self._lock:
            c = self._conn()
            try:
                row = c.execute("SELECT * FROM access_tokens WHERE token = ?", (token,)).fetchone()
            finally:
                c.close()
        return _token_row(row) if row else None

    def revoke_access_token(self, token: str) -> bool:
        with self._lock:
            c = self._conn()
            try:
                cur = c.execute("UPDATE access_tokens SET is_revoked = 1 WHERE token = ?",
                                (token,))
                c.commit()
                return cur.rowcount > 0
            finally:
                c.close()

    def list_tokens(self, app_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            c = self._conn()
            try:
                if app_id:
                    rows = c.execute(
                        "SELECT * FROM access_tokens WHERE app_id = ? ORDER BY issued_at DESC",
                        (app_id,),
                    ).fetchall()
                else:
                    rows = c.execute(
                        "SELECT * FROM access_tokens ORDER BY issued_at DESC"
                    ).fetchall()
            finally:
                c.close()
        return [_token_row(r) for r in rows]

    # -- logs --

    def append_log(self, entry: dict) -> None:
        import time as _t
        ts = float(entry.get("ts", _t.time()))
        app_id = str(entry.get("app_id") or "")
        body = json.dumps({k: v for k, v in entry.items() if k not in ("ts", "app_id")})
        with self._lock:
            c = self._conn()
            try:
                c.execute("INSERT INTO logs (ts, app_id, entry) VALUES (?, ?, ?)",
                          (ts, app_id, body))
                c.commit()
            finally:
                c.close()

    def list_logs(self, limit: int = 100, offset: int = 0,
                  app_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            c = self._conn()
            try:
                if app_id is not None:
                    rows = c.execute(
                        "SELECT * FROM logs WHERE app_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                        (app_id, limit, offset),
                    ).fetchall()
                else:
                    rows = c.execute(
                        "SELECT * FROM logs ORDER BY id DESC LIMIT ? OFFSET ?",
                        (limit, offset),
                    ).fetchall()
            finally:
                c.close()
        out = []
        for r in rows:
            e = json.loads(r["entry"])
            e["ts"] = r["ts"]
            if r["app_id"]:
                e["app_id"] = r["app_id"]
            out.append(e)
        return out


def _app_row(r: sqlite3.Row) -> dict:
    return {
        "app_id": r["app_id"],
        "app_secret": r["app_secret"],
        "name": r["name"],
        "redirect_uris": json.loads(r["redirect_uris"]),
        "date_created": r["date_created"],
        "date_updated": r["date_updated"],
    }


def _user_row(r: sqlite3.Row) -> dict:
    return {
        "app_id": r["app_id"],
        "fb_id": r["fb_id"],
        "name": r["name"],
        "email": r["email"],
        "granted_scopes": json.loads(r["granted_scopes"]),
        "simulate_invalid": bool(r["simulate_invalid"]),
        "simulate_expired": bool(r["simulate_expired"]),
        "date_created": r["date_created"],
        "date_updated": r["date_updated"],
    }


def _code_row(r: sqlite3.Row) -> dict:
    return {
        "code": r["code"],
        "app_id": r["app_id"],
        "user_fb_id": r["user_fb_id"],
        "redirect_uri": r["redirect_uri"],
        "scopes": json.loads(r["scopes"]),
        "expires_at": r["expires_at"],
        "consumed": bool(r["consumed"]),
    }


def _token_row(r: sqlite3.Row) -> dict:
    return {
        "token": r["token"],
        "app_id": r["app_id"],
        "user_fb_id": r["user_fb_id"],
        "scopes": json.loads(r["scopes"]),
        "issued_at": r["issued_at"],
        "expires_at": r["expires_at"],
        "is_revoked": bool(r["is_revoked"]),
    }

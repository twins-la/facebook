"""Abstract storage interface for the Facebook twin.

Hosts provide concrete implementations (SQLite, Postgres, in-memory).
The twin package never imports a specific database driver.

Every resource carries ``tenant_id`` (the twins.la platform tenant).
Apps and users are resources owned by a tenant; fb_id remains unique
within an app (not across the tenant).

Dicts on the wire between twin and storage use these keys:

App:
    app_id, tenant_id, app_secret, name, redirect_uris (list[str]),
    date_created, date_updated
User:
    fb_id, app_id, tenant_id, name, email, granted_scopes (list[str]),
    simulate_invalid (bool), simulate_expired (bool),
    date_created, date_updated
AuthCode:
    code, app_id, user_fb_id, redirect_uri, scopes (list[str]),
    expires_at (unix ts), consumed (bool)
AccessToken:
    token, app_id, user_fb_id, scopes (list[str]),
    issued_at (unix ts), expires_at (unix ts),
    is_revoked (bool)
Log:
    operation, tenant_id, app_id (optional), ..., ts
"""

from abc import ABC, abstractmethod
from typing import Optional


class FacebookTwinStorage(ABC):
    """Storage backend contract that hosts must implement."""

    # -- Apps --

    @abstractmethod
    def create_app_record(self, data: dict) -> dict:
        """Create an app. data must include app_id, app_secret, name, redirect_uris."""

    @abstractmethod
    def get_app(self, app_id: str) -> Optional[dict]:
        """Fetch an app by id."""

    @abstractmethod
    def list_apps(self, tenant_id: Optional[str] = None) -> list[dict]:
        """List apps, optionally scoped to a tenant. None means all apps (admin)."""

    @abstractmethod
    def delete_app(self, app_id: str) -> bool:
        """Delete an app and all its dependent data (users, codes, tokens).
        Returns True if deleted."""

    # -- Users --

    @abstractmethod
    def create_user(self, data: dict) -> dict:
        """Create a test user. data must include app_id, fb_id, name; email and
        granted_scopes optional."""

    @abstractmethod
    def get_user(self, app_id: str, fb_id: str) -> Optional[dict]:
        """Fetch a user by (app_id, fb_id). Returns None if the user exists
        but does not belong to app_id — implementations MUST NOT leak users
        across apps."""

    @abstractmethod
    def list_users(self, app_id: Optional[str] = None) -> list[dict]:
        """List users, optionally scoped to one app. None means all apps (admin)."""

    @abstractmethod
    def update_user(self, app_id: str, fb_id: str, updates: dict) -> Optional[dict]:
        """Update user fields within one app. Returns None if user not found
        in that app."""

    @abstractmethod
    def delete_user(self, app_id: str, fb_id: str) -> bool:
        """Delete a user within one app. Returns True if deleted."""

    # -- Authorization codes --

    @abstractmethod
    def create_auth_code(self, data: dict) -> dict:
        """Record an authorization code."""

    @abstractmethod
    def consume_auth_code(self, code: str) -> Optional[dict]:
        """Atomically fetch + mark consumed. Returns the code record or None if
        unknown / already consumed / expired. Implementation MUST treat this as
        one-shot; a second call for the same code returns None."""

    # -- Access tokens --

    @abstractmethod
    def create_access_token(self, data: dict) -> dict:
        """Store an access token."""

    @abstractmethod
    def get_access_token(self, token: str) -> Optional[dict]:
        """Look up an access token."""

    @abstractmethod
    def revoke_access_token(self, token: str) -> bool:
        """Mark an access token revoked. Returns True if the token existed."""

    @abstractmethod
    def list_tokens(self, app_id: Optional[str] = None) -> list[dict]:
        """List access tokens, optionally scoped to one app."""

    # -- Logs --

    @abstractmethod
    def append_log(self, entry: dict) -> None:
        """Append a log entry. Must set ts server-side if not present."""

    @abstractmethod
    def list_logs(self, limit: int = 100, offset: int = 0,
                  tenant_id: Optional[str] = None) -> list[dict]:
        """Retrieve operation logs, optionally scoped to one tenant."""

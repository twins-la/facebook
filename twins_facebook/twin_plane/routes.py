"""Twin Plane management API.

Served at /_twin/ — separate from the Facebook emulation surface.

Unauthenticated read-only endpoints:
    GET /_twin/health
    GET /_twin/scenarios
    GET /_twin/references
    GET /_twin/settings

Admin endpoints (require admin token):
    POST   /_twin/apps                   — create an app
    GET    /_twin/apps                   — list apps
    DELETE /_twin/apps/<app_id>          — delete an app
    POST   /_twin/users                             — create a test user (body includes app_id)
    GET    /_twin/users[?app_id=<id>]                — list users, optionally scoped
    PATCH  /_twin/apps/<app_id>/users/<fb_id>        — update user within an app
    DELETE /_twin/apps/<app_id>/users/<fb_id>        — delete user within an app
    PUT    /_twin/settings                           — update twin settings (e.g., interactive_dialog)

Tenant (app_id:app_secret Basic Auth) or admin:
    POST /_twin/tokens                   — issue an access token directly
                                           (body: fb_id, scopes) without walking the dialog
    GET  /_twin/logs                     — list operation logs; tenant sees only own app
"""

import logging

from flask import Blueprint, current_app, g, jsonify, request

from ..ids import (
    generate_app_id,
    generate_app_secret,
    generate_user_access_token,
    generate_user_fb_id,
)
from ..models import app_to_full, app_to_public, now_ts, user_to_admin
from ..versions import SUPPORTED_VERSIONS
from .auth import require_admin, require_admin_or_tenant

logger = logging.getLogger(__name__)

twin_plane_bp = Blueprint("twin_plane", __name__, url_prefix="/_twin")

_DEFAULT_TOKEN_TTL = 60 * 60 * 24 * 60


# -- Unauth info endpoints --


@twin_plane_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "twin": "facebook", "version": "0.1.0"})


@twin_plane_bp.route("/scenarios", methods=["GET"])
def scenarios():
    return jsonify({
        "scenarios": [
            {
                "name": "facebook-login",
                "status": "supported",
                "description": "Facebook Login — OAuth 2.0 authorization, "
                               "token exchange, Graph /me, and token inspection.",
                "api_versions": list(SUPPORTED_VERSIONS),
                "capabilities": [
                    "oauth_authorization_code_flow",
                    "oauth_implicit_flow",
                    "oauth_token_exchange",
                    "app_access_token",
                    "graph_me_field_selection",
                    "debug_token_inspection",
                    "redirect_uri_allowlisting",
                    "state_round_trip",
                    "user_cancel_simulation",
                    "invalid_and_expired_token_simulation",
                    "missing_email_simulation",
                ],
            }
        ]
    })


@twin_plane_bp.route("/references", methods=["GET"])
def references():
    return jsonify({
        "references": [
            {
                "title": "Facebook Login — Manually Build a Login Flow",
                "url": "https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow",
                "retrieved": "2026-04-12",
            },
            {
                "title": "Graph API — Access Tokens",
                "url": "https://developers.facebook.com/docs/facebook-login/guides/access-tokens",
                "retrieved": "2026-04-12",
            },
            {
                "title": "Graph API — /me User endpoint",
                "url": "https://developers.facebook.com/docs/graph-api/reference/user/",
                "retrieved": "2026-04-12",
            },
            {
                "title": "Graph API — /debug_token",
                "url": "https://developers.facebook.com/docs/graph-api/reference/v19.0/debug_token",
                "retrieved": "2026-04-12",
            },
            {
                "title": "Graph API — Error Handling",
                "url": "https://developers.facebook.com/docs/graph-api/guides/error-handling/",
                "retrieved": "2026-04-12",
            },
            {
                "title": "Graph API — Changelog & supported versions",
                "url": "https://developers.facebook.com/docs/graph-api/changelog/",
                "retrieved": "2026-04-12",
            },
        ]
    })


@twin_plane_bp.route("/settings", methods=["GET"])
def get_settings():
    s = current_app.config.get("TWIN_SETTINGS", {})
    return jsonify({
        "twin": "facebook",
        "version": "0.1.0",
        "base_url": g.base_url,
        "supported_versions": list(SUPPORTED_VERSIONS),
        "interactive_dialog": bool(s.get("interactive_dialog", False)),
    })


@twin_plane_bp.route("/settings", methods=["PUT"])
@require_admin
def put_settings():
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = request.json or {}
    s = current_app.config.setdefault("TWIN_SETTINGS", {})
    if "interactive_dialog" in data:
        s["interactive_dialog"] = bool(data["interactive_dialog"])
    return jsonify({"settings": dict(s)})


# -- Apps --


@twin_plane_bp.route("/apps", methods=["POST"])
@require_admin
def create_app_record():
    data = request.get_json(silent=True) or {}
    app_id = data.get("app_id") or generate_app_id()
    app_secret = data.get("app_secret") or generate_app_secret()
    name = data.get("name") or f"Test App {app_id[-6:]}"
    redirect_uris = list(data.get("redirect_uris") or [])
    if not redirect_uris:
        return jsonify({"error": "'redirect_uris' must be a non-empty list"}), 400

    now = now_ts()
    record = g.storage.create_app_record({
        "app_id": app_id,
        "app_secret": app_secret,
        "name": name,
        "redirect_uris": redirect_uris,
        "date_created": now,
        "date_updated": now,
    })
    g.storage.append_log({
        "operation": "twin.app.create",
        "app_id": app_id,
    })
    return jsonify(app_to_full(record)), 201


@twin_plane_bp.route("/apps", methods=["GET"])
@require_admin
def list_apps():
    return jsonify({"apps": [app_to_public(a) for a in g.storage.list_apps()]})


@twin_plane_bp.route("/apps/<app_id>", methods=["GET"])
@require_admin
def get_app_record(app_id: str):
    a = g.storage.get_app(app_id)
    if not a:
        return jsonify({"error": "App not found"}), 404
    return jsonify(app_to_public(a))


@twin_plane_bp.route("/apps/<app_id>", methods=["DELETE"])
@require_admin
def delete_app_record(app_id: str):
    ok = g.storage.delete_app(app_id)
    if not ok:
        return jsonify({"error": "App not found"}), 404
    g.storage.append_log({"operation": "twin.app.delete", "app_id": app_id})
    return "", 204


# -- Users --


@twin_plane_bp.route("/users", methods=["POST"])
@require_admin
def create_user():
    """Create a test user owned by a specific app. `app_id` in the body identifies
    the owner. Users are scoped per-app — the same fb_id can exist under different
    apps without collision, and tenants can never see users that don't belong to
    their app."""
    data = request.get_json(silent=True) or {}
    app_id = data.get("app_id")
    if not app_id:
        return jsonify({"error": "'app_id' is required — users are scoped per-app"}), 400
    if not g.storage.get_app(app_id):
        return jsonify({"error": "App not found"}), 404
    fb_id = data.get("fb_id") or generate_user_fb_id()
    now = now_ts()
    record = g.storage.create_user({
        "app_id": app_id,
        "fb_id": fb_id,
        "name": data.get("name") or f"Test User {fb_id[-4:]}",
        "email": data.get("email", ""),
        "granted_scopes": list(data.get("granted_scopes") or []),
        "simulate_invalid": bool(data.get("simulate_invalid", False)),
        "simulate_expired": bool(data.get("simulate_expired", False)),
        "date_created": now,
        "date_updated": now,
    })
    g.storage.append_log({"operation": "twin.user.create",
                          "app_id": app_id, "user_fb_id": fb_id})
    return jsonify(user_to_admin(record)), 201


@twin_plane_bp.route("/users", methods=["GET"])
@require_admin
def list_users():
    """Admin listing; optional ?app_id=… filter."""
    app_id = request.args.get("app_id")
    return jsonify({"users": [user_to_admin(u) for u in g.storage.list_users(app_id)]})


@twin_plane_bp.route("/apps/<app_id>/users/<fb_id>", methods=["PATCH"])
@require_admin
def update_user(app_id: str, fb_id: str):
    data = request.get_json(silent=True) or {}
    allowed = {"name", "email", "granted_scopes", "simulate_invalid", "simulate_expired"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if "granted_scopes" in updates:
        updates["granted_scopes"] = list(updates["granted_scopes"])
    updates["date_updated"] = now_ts()
    record = g.storage.update_user(app_id, fb_id, updates)
    if not record:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user_to_admin(record))


@twin_plane_bp.route("/apps/<app_id>/users/<fb_id>", methods=["DELETE"])
@require_admin
def delete_user(app_id: str, fb_id: str):
    ok = g.storage.delete_user(app_id, fb_id)
    if not ok:
        return jsonify({"error": "User not found"}), 404
    return "", 204


# -- Direct token issuance (for fixture-style tests) --


@twin_plane_bp.route("/tokens", methods=["POST"])
@require_admin_or_tenant
def mint_token():
    """Mint an access token for (app_id, fb_id). Tenants can only mint for
    users in their own app — cross-tenant mints are rejected at the user
    lookup step because users are per-app scoped."""
    data = request.get_json(silent=True) or {}
    fb_id = data.get("fb_id")
    if not fb_id:
        return jsonify({"error": "'fb_id' is required"}), 400

    # Tenant mode: token is issued for g.app. Admin mode: app_id in body.
    if g.is_admin:
        app_id = data.get("app_id")
        if not app_id:
            return jsonify({"error": "'app_id' is required for admin mints"}), 400
        if not g.storage.get_app(app_id):
            return jsonify({"error": "App not found"}), 404
    else:
        app_id = g.app_id

    # Per-app scoped user lookup — a tenant cannot mint for another app's user
    # even if they guess/leak the fb_id.
    if not g.storage.get_user(app_id, fb_id):
        return jsonify({"error": "User not found"}), 404

    scopes = list(data.get("scopes") or [])
    ttl = int(data.get("expires_in", _DEFAULT_TOKEN_TTL))
    now = now_ts()
    token = generate_user_access_token()
    g.storage.create_access_token({
        "token": token,
        "app_id": app_id,
        "user_fb_id": fb_id,
        "scopes": scopes,
        "issued_at": now,
        "expires_at": now + ttl,
        "is_revoked": False,
    })
    g.storage.append_log({
        "operation": "twin.token.mint",
        "app_id": app_id,
        "user_fb_id": fb_id,
    })
    return jsonify({
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl,
        "scopes": scopes,
    }), 201


# -- Logs --


@twin_plane_bp.route("/logs", methods=["GET"])
@require_admin_or_tenant
def logs():
    limit = request.args.get("limit", 100, type=int)
    limit = max(1, min(limit, 1000))  # cap to avoid DB-streaming DoS
    offset = max(0, request.args.get("offset", 0, type=int))
    app_id = None if g.is_admin else g.app_id
    entries = g.storage.list_logs(limit=limit, offset=offset, app_id=app_id)
    return jsonify({"logs": entries, "limit": limit, "offset": offset})

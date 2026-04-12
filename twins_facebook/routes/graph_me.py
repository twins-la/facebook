"""Graph API /me endpoint.

GET /v<ver>/me?fields=id,name,email
  Authorization: Bearer <token>         (or)
  ?access_token=<token>                  (or)
  form-encoded access_token=<token>

Returns a Facebook-shape user JSON restricted to the requested fields.
Real Facebook also allows GET /v<ver>/<user_id> to the same effect; we
implement that too for symmetry.
"""

import logging

from flask import Blueprint, g, jsonify, request

from ..errors import (
    expired_access_token,
    invalid_access_token,
    missing_parameter,
    revoked_access_token,
    unsupported_api_version,
    fb_error,
)
from ..models import ME_FIELDS_ALL, now_ts, project_me, unknown_me_fields
from ..versions import is_supported_version

logger = logging.getLogger(__name__)

graph_me_bp = Blueprint("graph_me", __name__)


def _extract_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip() or None
    return request.values.get("access_token") or None


def _resolve_token(token: str):
    """Return (token_record, user_record, error_response_or_None)."""
    if not token:
        return None, None, missing_parameter("access_token")

    rec = g.storage.get_access_token(token)
    if not rec:
        return None, None, invalid_access_token()
    if rec.get("is_revoked"):
        return None, None, revoked_access_token()
    if rec.get("expires_at", 0) < now_ts():
        return None, None, expired_access_token()

    # Per-app user lookup: token is bound to (app_id, user_fb_id).
    user = g.storage.get_user(rec["app_id"], rec["user_fb_id"])
    if not user:
        # Token valid but user deleted (or the app was deleted) — treat as revoked.
        return None, None, revoked_access_token()

    if user.get("simulate_invalid"):
        return None, None, invalid_access_token()
    if user.get("simulate_expired"):
        return None, None, expired_access_token()

    return rec, user, None


def _parse_fields(raw: str | None) -> list[str]:
    if not raw:
        return ["id", "name"]
    return [f.strip() for f in raw.split(",") if f.strip()]


def _me_impl(target_fb_id: str | None):
    token = _extract_token()
    rec, user, err = _resolve_token(token)
    if err is not None:
        return err

    if target_fb_id and target_fb_id != "me" and target_fb_id != user["fb_id"]:
        # Real Facebook allows reading other users only with permission;
        # our scenario is 'self lookup'. Return not-supported-like error.
        return fb_error(
            400, 100, "GraphMethodException",
            f"Unsupported get request. Object with ID '{target_fb_id}' "
            "does not exist or cannot be loaded due to missing permissions.",
        )

    fields = _parse_fields(request.args.get("fields"))
    unknown = unknown_me_fields(fields)
    if unknown:
        return fb_error(
            400, 100, "GraphMethodException",
            f"(#100) Tried accessing nonexisting field ({unknown[0]}) on node type (User)",
        )

    g.storage.append_log({
        "operation": "graph.me.fetch",
        "app_id": rec["app_id"],
        "user_fb_id": user["fb_id"],
        "fields": fields,
    })

    return jsonify(project_me(user, fields))


@graph_me_bp.route("/<version>/me", methods=["GET"])
def me(version: str):
    if not is_supported_version(version):
        return unsupported_api_version(version)
    return _me_impl("me")


@graph_me_bp.route("/<version>/<fb_user_id>", methods=["GET"])
def user_by_id(version: str, fb_user_id: str):
    if not is_supported_version(version):
        return unsupported_api_version(version)
    # Avoid shadowing other concrete routes that happen to live under
    # /v<ver>/<name>, like /v19.0/oauth and /v19.0/debug_token.
    if fb_user_id in {"oauth", "debug_token", "me", "dialog"}:
        return fb_error(
            404, 803, "GraphMethodException",
            f"Unsupported get request. Object with ID '{fb_user_id}' does not exist.",
        )
    return _me_impl(fb_user_id)

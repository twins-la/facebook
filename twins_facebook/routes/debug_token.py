"""Token inspection endpoint.

GET /v<ver>/debug_token?input_token=<tok>&access_token=<app-or-user-tok>

Returns:
    {"data": {"app_id": "...", "type": "USER", "application": "<name>",
              "user_id": "...", "is_valid": true|false,
              "expires_at": <ts>, "issued_at": <ts>, "scopes": [...]}}

The caller MUST supply their own access_token — real Facebook requires
the caller to authenticate the inspection request. The returned app_id
is the app that issued input_token, which is how a consumer detects
token-substitution attacks (app_id != their expected app_id).
"""

import hmac
import logging

from flask import Blueprint, g, jsonify, request

from ..errors import (
    invalid_access_token,
    missing_parameter,
    unsupported_api_version,
)
from ..models import now_ts
from ..versions import is_supported_version

logger = logging.getLogger(__name__)

debug_token_bp = Blueprint("debug_token", __name__)


def _is_app_access_token(token: str) -> bool:
    """APP_ID|APP_SECRET shape."""
    return "|" in token and len(token.split("|", 1)) == 2


@debug_token_bp.route("/<version>/debug_token", methods=["GET"])
def debug(version: str):
    if not is_supported_version(version):
        return unsupported_api_version(version)

    input_token = request.args.get("input_token")
    caller_token = request.args.get("access_token")
    if not input_token:
        return missing_parameter("input_token")
    if not caller_token:
        # Caller must prove identity. A missing access_token is an
        # access-token failure (code 190), not a parameter failure
        # (code 100) — same logic as graph_me. See twins-la/facebook#1.
        return invalid_access_token()

    # Validate caller_token — accept either an app access token
    # (APP_ID|APP_SECRET) or a regular user access token. Invalid-but-present
    # caller tokens return OAuthException code 190, matching real Facebook.
    caller_app_id = None
    if _is_app_access_token(caller_token):
        app_id, secret = caller_token.split("|", 1)
        app = g.storage.get_app(app_id)
        if not app or not hmac.compare_digest(app["app_secret"], secret):
            return invalid_access_token()
        caller_app_id = app_id
    else:
        rec = g.storage.get_access_token(caller_token)
        if not rec:
            return invalid_access_token()
        caller_app_id = rec["app_id"]

    # Inspect input_token.
    data: dict = {"is_valid": False}

    if _is_app_access_token(input_token):
        app_id, secret = input_token.split("|", 1)
        app = g.storage.get_app(app_id)
        if app and hmac.compare_digest(app["app_secret"], secret):
            data = {
                "app_id": app_id,
                "type": "APP",
                "application": app.get("name", ""),
                "is_valid": True,
                "scopes": [],
            }
    else:
        rec = g.storage.get_access_token(input_token)
        if rec:
            app = g.storage.get_app(rec["app_id"])
            is_valid = (
                not rec.get("is_revoked", False)
                and rec.get("expires_at", 0) >= now_ts()
            )
            data = {
                "app_id": rec["app_id"],
                "type": "USER",
                "application": app.get("name", "") if app else "",
                "user_id": rec["user_fb_id"],
                "is_valid": is_valid,
                "issued_at": rec.get("issued_at"),
                "expires_at": rec.get("expires_at"),
                "scopes": list(rec.get("scopes", [])),
            }

    from twins_local.logs import ANONYMOUS_TENANT_ID
    from ..logs import emit

    caller_app = g.storage.get_app(caller_app_id) if caller_app_id else None
    _tid = (caller_app or {}).get("tenant_id") or ANONYMOUS_TENANT_ID
    emit(
        g.storage,
        tenant_id=_tid,
        plane="data",
        operation="token.debug",
        resource={"type": "app", "id": caller_app_id or ""},
        details={"inspected_app_id": data.get("app_id", "")},
    )

    return jsonify({"data": data})

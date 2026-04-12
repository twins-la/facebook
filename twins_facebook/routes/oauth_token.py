"""Token exchange endpoint.

GET /v<ver>/oauth/access_token?client_id=...&client_secret=...&redirect_uri=...&code=...
    → {"access_token": "...", "token_type": "bearer", "expires_in": <int>}

Real Facebook also supports app access tokens via
client_credentials-style calls (no code, with grant_type=client_credentials).
That is an app-level auth, not user-level — we support it too, returning
the canonical APP_ID|APP_SECRET token shape.

See https://developers.facebook.com/docs/facebook-login/guides/access-tokens
"""

import hmac
import logging

from flask import Blueprint, g, jsonify, request

from twins_local.logs import ANONYMOUS_TENANT_ID

from ..errors import (
    invalid_app_credentials,
    invalid_authorization_code,
    missing_parameter,
    redirect_uri_mismatch,
    unsupported_api_version,
)
from ..ids import generate_app_access_token, generate_user_access_token
from ..logs import emit
from ..models import now_ts
from ..versions import is_supported_version

logger = logging.getLogger(__name__)

oauth_token_bp = Blueprint("oauth_token", __name__)

_DEFAULT_TOKEN_TTL = 60 * 60 * 24 * 60  # ~60 days


@oauth_token_bp.route("/<version>/oauth/access_token", methods=["GET", "POST"])
def exchange(version: str):
    if not is_supported_version(version):
        return unsupported_api_version(version)

    src = request.values  # merges args + form

    client_id = src.get("client_id")
    client_secret = src.get("client_secret")
    if not client_id:
        return missing_parameter("client_id")
    if not client_secret:
        return missing_parameter("client_secret")

    app = g.storage.get_app(client_id)
    if not app or not hmac.compare_digest(app["app_secret"], client_secret):
        return invalid_app_credentials()

    grant_type = src.get("grant_type")
    if grant_type == "client_credentials":
        # App access token path.
        token = generate_app_access_token(client_id, client_secret)
        _app = g.storage.get_app(client_id)
        _tid = (_app or {}).get("tenant_id") or ANONYMOUS_TENANT_ID
        emit(
            g.storage,
            tenant_id=_tid,
            plane="data",
            operation="oauth.token.app_token_issued",
            resource={"type": "app", "id": client_id},
        )
        return jsonify({"access_token": token, "token_type": "bearer"})

    redirect_uri = src.get("redirect_uri")
    code = src.get("code")
    if not redirect_uri:
        return missing_parameter("redirect_uri")
    if not code:
        return missing_parameter("code")

    record = g.storage.consume_auth_code(code)
    if record is None:
        return invalid_authorization_code()

    now = now_ts()
    if record.get("expires_at", 0) < now:
        return invalid_authorization_code()
    if record.get("app_id") != client_id:
        return invalid_app_credentials()
    if record.get("redirect_uri") != redirect_uri:
        return redirect_uri_mismatch()

    token = generate_user_access_token()
    g.storage.create_access_token({
        "token": token,
        "app_id": client_id,
        "user_fb_id": record["user_fb_id"],
        "scopes": list(record.get("scopes", [])),
        "issued_at": now,
        "expires_at": now + _DEFAULT_TOKEN_TTL,
        "is_revoked": False,
    })
    _app = g.storage.get_app(client_id)
    _tid = (_app or {}).get("tenant_id") or ANONYMOUS_TENANT_ID
    emit(
        g.storage,
        tenant_id=_tid,
        plane="data",
        operation="oauth.token.user_token_issued",
        resource={"type": "app", "id": client_id},
        details={"user_fb_id": record["user_fb_id"]},
    )
    return jsonify({
        "access_token": token,
        "token_type": "bearer",
        "expires_in": _DEFAULT_TOKEN_TTL,
    })

"""OAuth authorization dialog.

Emulates https://www.facebook.com/v<ver>/dialog/oauth and the bare path
/dialog/oauth. Supports response_type=code (authorization-code flow) and
response_type=token (implicit flow).

The dialog is auto-approved by default so automated tests can walk the
full flow without UI. Setting the twin-plane flag `interactive_dialog=true`
renders an HTML consent page.

Twin-specific query knobs (prefixed `twin_`):
  twin_user_id  — pick which configured test user signs in. If absent and
                  there is exactly one user configured, that user is used.
                  Otherwise the dialog returns a consent form listing users.
  twin_simulate — one of {approve, denied}. 'denied' redirects with
                  error=access_denied.
"""

import logging
import time
import urllib.parse

from flask import Blueprint, g, redirect, request
from jinja2 import Environment, select_autoescape

from twins_local.logs import ANONYMOUS_TENANT_ID

from ..ids import generate_authorization_code, generate_user_access_token
from ..logs import emit
from ..models import now_ts
from ..versions import SUPPORTED_VERSIONS, is_supported_version

logger = logging.getLogger(__name__)

oauth_dialog_bp = Blueprint("oauth_dialog", __name__)

_DEFAULT_CODE_TTL = 600
_DEFAULT_TOKEN_TTL = 60 * 60 * 24 * 60  # ~60 days


# Dedicated Jinja environment with explicit autoescape. Flask's
# render_template_string does NOT autoescape string templates by default
# (autoescape keys off template filename), so we build our own env with
# autoescape forced on for anything that looks like HTML. This protects
# the reflected fields (app name, user name, user email) from stored XSS.
_JINJA_ENV = Environment(autoescape=select_autoescape(default=True, default_for_string=True))

_CONSENT_TEMPLATE_SRC = """<!doctype html>
<html><head><meta charset="utf-8"><title>Log in with Facebook (twin)</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 480px; margin: 2rem auto;">
<h2>Log in with Facebook (twin)</h2>
<p><b>{{ app_name }}</b> is requesting access with scopes: <code>{{ scopes_display }}</code></p>
<p>This is a twins.la twin of Facebook, not real Facebook.</p>
<form method="post" action="{{ action }}">
  {% for k, v in hidden.items() %}<input type="hidden" name="{{ k }}" value="{{ v }}">{% endfor %}
  <label>Sign in as:
    <select name="twin_user_id">
      {% for u in users %}<option value="{{ u.fb_id }}">{{ u.name }} ({{ u.email or 'no email' }})</option>{% endfor %}
    </select>
  </label>
  <p>
    <button type="submit" name="twin_simulate" value="approve">Continue</button>
    <button type="submit" name="twin_simulate" value="denied">Cancel</button>
  </p>
</form>
</body></html>
"""

_CONSENT_TEMPLATE = _JINJA_ENV.from_string(_CONSENT_TEMPLATE_SRC)


def _parse_scopes(raw: str) -> list[str]:
    if not raw:
        return []
    return [s.strip() for s in raw.replace(",", " ").split() if s.strip()]


def _pick_user(storage, app_id: str, twin_user_id: str | None):
    """Pick a test user scoped to the given app_id.

    Per-app scoping: only users owned by `app_id` are visible to this dialog,
    so a tenant cannot exfiltrate another app's user PII via the dialog flow.
    """
    users = storage.list_users(app_id=app_id)
    if twin_user_id:
        for u in users:
            if u["fb_id"] == twin_user_id:
                return u, users
        return None, users
    if len(users) == 1:
        return users[0], users
    return None, users


def _error_redirect(redirect_uri: str, state: str, error: str,
                    reason: str = "", description: str = "", fragment: bool = False):
    # Always echo state — including empty string — to mirror real Facebook.
    params: list[tuple[str, str]] = [("error", error)]
    if reason:
        params.append(("error_reason", reason))
    if description:
        params.append(("error_description", description))
    params.append(("state", state or ""))
    qs = urllib.parse.urlencode(params)
    sep = "#" if fragment else ("&" if "?" in redirect_uri else "?")
    return redirect(f"{redirect_uri}{sep}{qs}", code=302)


def _success_redirect_code(redirect_uri: str, code: str, state: str):
    sep = "&" if "?" in redirect_uri else "?"
    qs = urllib.parse.urlencode({"code": code, "state": state or ""})
    return redirect(f"{redirect_uri}{sep}{qs}", code=302)


def _success_redirect_token(redirect_uri: str, token: str, expires_in: int, state: str):
    qs = urllib.parse.urlencode({
        "access_token": token,
        "token_type": "bearer",
        "expires_in": str(expires_in),
        "state": state or "",
    })
    return redirect(f"{redirect_uri}#{qs}", code=302)


def _handle_dialog():
    storage = g.storage
    # Support GET (typical) and POST (from consent form submit)
    src = request.form if request.method == "POST" else request.args

    client_id = src.get("client_id") or ""
    redirect_uri = src.get("redirect_uri") or ""
    state = src.get("state") or ""
    response_type = src.get("response_type") or "code"
    scope_raw = src.get("scope") or ""
    scopes = _parse_scopes(scope_raw)
    twin_user_id = src.get("twin_user_id")
    twin_simulate = src.get("twin_simulate", "approve")

    if not client_id or not redirect_uri:
        return _plain_error_page(
            "Missing client_id or redirect_uri. Real Facebook returns an error page here.",
            400,
        )

    app = storage.get_app(client_id)
    if not app:
        return _plain_error_page(
            "Unknown application. The app_id is not registered on this twin.", 400,
        )
    if redirect_uri not in app.get("redirect_uris", []):
        return _plain_error_page(
            "The redirect_uri is not registered for this app. "
            "Register it via POST /_twin/apps before attempting login.", 400,
        )
    if response_type not in ("code", "token"):
        return _plain_error_page(
            f"Unsupported response_type: {response_type}. Expected 'code' or 'token'.", 400,
        )

    settings = g.settings
    interactive = bool(settings.get("interactive_dialog", False))

    # Interactive mode without a form submission — render consent page.
    if interactive and request.method == "GET":
        users = storage.list_users(app_id=client_id)
        hidden = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": response_type,
            "scope": scope_raw,
        }
        return _CONSENT_TEMPLATE.render(
            app_name=app.get("name", client_id),
            scopes_display=", ".join(scopes) if scopes else "(none)",
            action=request.path,
            hidden=hidden,
            users=users,
        )

    # Simulated denial.
    if twin_simulate == "denied":
        frag = response_type == "token"
        _app = storage.get_app(client_id)
        _tid = (_app or {}).get("tenant_id") or ANONYMOUS_TENANT_ID
        emit(
            storage,
            tenant_id=_tid,
            plane="data",
            operation="oauth.dialog.denied",
            resource={"type": "app", "id": client_id},
            outcome="failure",
            reason="user_denied",
            details={"redirect_uri": redirect_uri},
        )
        return _error_redirect(
            redirect_uri, state,
            error="access_denied", reason="user_denied",
            description="Permissions error",
            fragment=frag,
        )

    user, users = _pick_user(storage, client_id, twin_user_id)
    if user is None:
        if not users:
            return _plain_error_page(
                f"No test users configured on app {client_id}. "
                "Create one via POST /_twin/users (with app_id) before walking the dialog flow.", 400,
            )
        # Multiple users and no twin_user_id — render a picker even in non-interactive mode.
        hidden = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": response_type,
            "scope": scope_raw,
        }
        return _CONSENT_TEMPLATE.render(
            app_name=app.get("name", client_id),
            scopes_display=", ".join(scopes) if scopes else "(none)",
            action=request.path,
            hidden=hidden,
            users=users,
        )

    now = now_ts()

    if response_type == "code":
        code = generate_authorization_code()
        storage.create_auth_code({
            "code": code,
            "app_id": client_id,
            "user_fb_id": user["fb_id"],
            "redirect_uri": redirect_uri,
            "scopes": scopes,
            "expires_at": now + _DEFAULT_CODE_TTL,
            "consumed": False,
        })
        _app = storage.get_app(client_id)
        _tid = (_app or {}).get("tenant_id") or ANONYMOUS_TENANT_ID
        emit(
            storage,
            tenant_id=_tid,
            plane="data",
            operation="oauth.dialog.code_issued",
            resource={"type": "app", "id": client_id},
            details={
                "user_fb_id": user["fb_id"],
                "redirect_uri": redirect_uri,
            },
        )
        return _success_redirect_code(redirect_uri, code, state)

    # implicit flow
    token = generate_user_access_token()
    storage.create_access_token({
        "token": token,
        "app_id": client_id,
        "user_fb_id": user["fb_id"],
        "scopes": scopes,
        "issued_at": now,
        "expires_at": now + _DEFAULT_TOKEN_TTL,
        "is_revoked": False,
    })
    _app = storage.get_app(client_id)
    _tid = (_app or {}).get("tenant_id") or ANONYMOUS_TENANT_ID
    emit(
        storage,
        tenant_id=_tid,
        plane="data",
        operation="oauth.dialog.token_issued",
        resource={"type": "app", "id": client_id},
        details={"user_fb_id": user["fb_id"], "scopes": scopes},
    )
    return _success_redirect_token(redirect_uri, token, _DEFAULT_TOKEN_TTL, state)


def _plain_error_page(message: str, http_status: int):
    # Escape the message — some callers reflect user input (e.g., response_type
    # from the query string) and we don't want that to be an XSS vector.
    from markupsafe import escape
    body = (
        f"<!doctype html><html><body style='font-family: system-ui, sans-serif;'>"
        f"<h3>Facebook Login (twin) — error</h3><p>{escape(message)}</p></body></html>"
    )
    return body, http_status, {"Content-Type": "text/html; charset=utf-8"}


# Mount at unversioned /dialog/oauth AND at /v<ver>/dialog/oauth.
@oauth_dialog_bp.route("/dialog/oauth", methods=["GET", "POST"])
def dialog_oauth_unversioned():
    return _handle_dialog()


@oauth_dialog_bp.route("/<version>/dialog/oauth", methods=["GET", "POST"])
def dialog_oauth_versioned(version: str):
    if not is_supported_version(version):
        return _plain_error_page(f"Unknown API version: {version}", 400)
    return _handle_dialog()

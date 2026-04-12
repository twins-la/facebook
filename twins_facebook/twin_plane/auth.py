"""Twin Plane authentication.

Two auth modes:

- Admin: header `X-Twin-Admin-Token: <admin_token>` or
  `Authorization: Bearer <admin_token>`. Admin ops can read across apps.

- Tenant: HTTP Basic Auth with app_id:app_secret. Tenant ops are scoped
  to one app.

Both modes set g.is_admin (bool). For tenant auth, g.app_id and g.app
are also set.
"""

import functools
import hmac

from flask import g, jsonify, request


def _auth_error(message: str = "Authentication required"):
    resp = jsonify({"error": message})
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = 'Basic realm="Twin Plane"'
    return resp


def _check_admin_token() -> bool:
    """True if the request presents a valid admin token."""
    admin_token = g.admin_token
    supplied = None
    header = request.headers.get("X-Twin-Admin-Token", "")
    if header:
        supplied = header
    else:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            supplied = auth_header[7:]
    if supplied is None:
        return False
    if not admin_token:
        # Unset admin token means "accept any bearer" — local dev only.
        return True
    return hmac.compare_digest(admin_token, supplied)


def require_admin(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not _check_admin_token():
            return _auth_error()
        g.is_admin = True
        g.app_id = None
        g.app = None
        return f(*args, **kwargs)
    return wrapper


def require_admin_or_tenant(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if _check_admin_token():
            g.is_admin = True
            g.app_id = None
            g.app = None
            return f(*args, **kwargs)

        auth = request.authorization
        if not auth or not auth.username or not auth.password:
            return _auth_error()
        app = g.storage.get_app(auth.username)
        if not app or not hmac.compare_digest(app["app_secret"], auth.password):
            return _auth_error()
        g.is_admin = False
        g.app_id = app["app_id"]
        g.app = app
        return f(*args, **kwargs)
    return wrapper

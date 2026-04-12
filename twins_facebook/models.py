"""Serialization helpers that produce Facebook-shaped JSON.

Kept in one place so routes don't re-implement field selection or public
projections.
"""

import time


def now_ts() -> int:
    return int(time.time())


def app_to_public(app: dict) -> dict:
    """App dict as exposed by Twin Plane reads (secret redacted)."""
    return {
        "app_id": app["app_id"],
        "name": app.get("name", ""),
        "redirect_uris": list(app.get("redirect_uris", [])),
        "date_created": app.get("date_created"),
    }


def app_to_full(app: dict) -> dict:
    """App dict as returned immediately after creation (includes secret)."""
    out = app_to_public(app)
    out["app_secret"] = app["app_secret"]
    return out


def user_to_admin(user: dict) -> dict:
    """User dict as exposed through Twin Plane."""
    return {
        "app_id": user.get("app_id", ""),
        "fb_id": user["fb_id"],
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "granted_scopes": list(user.get("granted_scopes", [])),
        "simulate_invalid": bool(user.get("simulate_invalid", False)),
        "simulate_expired": bool(user.get("simulate_expired", False)),
        "date_created": user.get("date_created"),
    }


# Canonical field list for /me. Field selection is a projection over this.
ME_FIELDS_ALL: tuple[str, ...] = ("id", "name", "email")


def project_me(user: dict, fields: list[str]) -> dict:
    """Return /me JSON restricted to requested fields.

    'email' is only ever returned when the user has granted the 'email' scope;
    if the caller requested it but the user did not grant it, it is simply
    omitted — this mirrors real Facebook.
    """
    out: dict = {}
    granted = set(user.get("granted_scopes", []))
    for f in fields:
        if f == "id":
            out["id"] = user["fb_id"]
        elif f == "name":
            out["name"] = user.get("name", "")
        elif f == "email":
            if "email" in granted and user.get("email"):
                out["email"] = user["email"]
    return out


def unknown_me_fields(fields: list[str]) -> list[str]:
    """Return the subset of requested fields that are not supported."""
    return [f for f in fields if f not in ME_FIELDS_ALL]

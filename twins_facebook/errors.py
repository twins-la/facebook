"""Facebook-format error responses.

Real Facebook errors use:
    {"error": {"message": "...", "type": "OAuthException",
               "code": 190, "fbtrace_id": "..."}}

See https://developers.facebook.com/docs/graph-api/guides/error-handling/
"""

from flask import jsonify

from .ids import generate_fbtrace_id


def fb_error(http_status: int, code: int, type_: str, message: str,
             error_subcode: int | None = None):
    body = {
        "error": {
            "message": message,
            "type": type_,
            "code": code,
            "fbtrace_id": generate_fbtrace_id(),
        }
    }
    if error_subcode is not None:
        body["error"]["error_subcode"] = error_subcode
    resp = jsonify(body)
    resp.status_code = http_status
    return resp


# -- OAuth/authentication errors --

def invalid_access_token():
    """code 190 — invalid or expired access token."""
    return fb_error(
        400, 190, "OAuthException",
        "Invalid OAuth access token.",
    )


def expired_access_token():
    """code 190, subcode 463 — token expired."""
    return fb_error(
        400, 190, "OAuthException",
        "Session has expired. Please log in again.",
        error_subcode=463,
    )


def revoked_access_token():
    """code 190, subcode 467 — token revoked."""
    return fb_error(
        400, 190, "OAuthException",
        "Access token has been revoked.",
        error_subcode=467,
    )


def invalid_app_credentials():
    """code 101 — unknown app or bad secret."""
    return fb_error(
        400, 101, "OAuthException",
        "Error validating application. Cannot get application info due to a system error.",
    )


def invalid_authorization_code():
    """code 100, subcode 36007 — authorization code invalid/expired/consumed."""
    return fb_error(
        400, 100, "OAuthException",
        "Invalid verification code format.",
        error_subcode=36007,
    )


def redirect_uri_mismatch():
    """code 191 — redirect_uri not registered or does not match the code."""
    return fb_error(
        400, 191, "OAuthException",
        "The redirect_uri URL must be an absolute URI registered for the app.",
    )


def missing_parameter(name: str):
    """code 100 — required parameter missing/invalid."""
    return fb_error(
        400, 100, "GraphMethodException",
        f"Missing or invalid parameter: {name}",
    )


def unsupported_api_version(version: str):
    """code 2500 — unsupported API version."""
    return fb_error(
        400, 2500, "GraphMethodException",
        f"Unknown API version: {version}",
    )


def unknown_path(path: str):
    """code 803 — unknown path / object not found."""
    return fb_error(
        404, 803, "GraphMethodException",
        f"Unsupported get request. Object with ID or path '{path}' does not exist.",
    )


def generic_oauth(message: str, http_status: int = 400, code: int = 1):
    return fb_error(http_status, code, "OAuthException", message)

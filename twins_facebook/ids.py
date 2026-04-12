"""Token, code, and identifier generation.

Tokens and codes are opaque twin values — consumers MUST NOT hard-code
real Facebook token structure (twins.la Principle 1). The EAA prefix on
user access tokens is a visual-similarity courtesy, not a fidelity
contract.
"""

import base64
import secrets


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_app_id() -> str:
    """Facebook-style numeric app_id (15-17 digits). The twin issues string digits."""
    return str(secrets.randbelow(10**17 - 10**15) + 10**15)


def generate_app_secret() -> str:
    """32-hex-character app secret."""
    return secrets.token_hex(16)


def generate_user_fb_id() -> str:
    """Facebook-style numeric user id."""
    return str(secrets.randbelow(10**17 - 10**14) + 10**14)


def generate_user_access_token() -> str:
    """Opaque user access token. EAA prefix mirrors real Facebook visually."""
    return "EAA" + _b64url(secrets.token_bytes(48))


def generate_app_access_token(app_id: str, app_secret: str) -> str:
    """App access token. Real Facebook returns 'APP_ID|APP_SECRET' here.

    We preserve that pipe-separated shape so consumers that parse it work
    unchanged against the twin.
    """
    return f"{app_id}|{app_secret}"


def generate_authorization_code() -> str:
    """Opaque short-lived authorization code (code-flow)."""
    return "AQ" + _b64url(secrets.token_bytes(48))


def generate_fbtrace_id() -> str:
    """Facebook-style trace id. 11-char base64url is close to the real shape."""
    return _b64url(secrets.token_bytes(8))[:11]

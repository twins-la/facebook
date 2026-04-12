"""Supported Facebook Graph API versions.

Real Facebook serves multiple Graph API versions concurrently at
https://graph.facebook.com/v<N>.0/... and users can pick any supported
version in their requests. This twin preserves that: every Graph-API
endpoint is mounted under every version in SUPPORTED_VERSIONS.

Adding a new version is additive — append to the tuple. Removing a
version is a breaking change to the scenario and requires a new job.
"""

SUPPORTED_VERSIONS: tuple[str, ...] = ("v19.0", "v21.0")


def is_supported_version(version: str) -> bool:
    return version in SUPPORTED_VERSIONS

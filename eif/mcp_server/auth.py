"""EIF API key authentication for the self-hosted HTTP server.

Single-key model: set EIF_API_KEY to any secret string and the HTTP server
requires that exact value as a Bearer token. This protects a self-hosted
EIF instance exposed beyond localhost.

Environment variables:
  EIF_API_KEY - the shared secret. If not set:
                  development: auth is bypassed (open local server)
                  production (EIF_ENV=production): ALL requests are rejected

Security note: this is a bearer token compared in constant time. It is not
an OAuth token and no external validation call is made. For multi-user
deployments, put a real gateway (or your own auth proxy) in front.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets

_log = logging.getLogger("eif.auth")

_API_KEY = os.environ.get("EIF_API_KEY", "")
_ENV = os.environ.get("EIF_ENV", "development")

# Dev test key - accepted in development mode only
_DEV_TEST_KEY = "dev-test-key"
_DEV_KEY_INFO = {"key_id": "dev00000", "is_dev": True}


class AuthError(Exception):
    pass


def validate_key(api_key: str) -> dict | None:
    """Validate an API key. Returns key_info dict or None if invalid.

    key_info: {"key_id": str, "is_dev": bool}
    """
    # Dev test key - allowed only in non-production
    if api_key == _DEV_TEST_KEY:
        if _ENV == "production":
            _log.warning("AUTH  dev test key rejected in production")
            return None
        return _DEV_KEY_INFO

    # No key configured on the server side
    if not _API_KEY:
        if _ENV == "production":
            _log.error("AUTH  EIF_API_KEY not set - rejecting all requests in production")
            return None
        _log.debug("AUTH  no EIF_API_KEY configured - open server (dev mode)")
        return {"key_id": "local", "is_dev": True}

    if not api_key:
        return None

    if not hmac.compare_digest(api_key, _API_KEY):
        return None

    return {"key_id": "self-host", "is_dev": False}


def require_api_key(api_key: str) -> dict:
    """Validate and return key_info. Raises AuthError if invalid."""
    info = validate_key(api_key)
    if info is None:
        raise AuthError(
            "Invalid or missing API key. "
            "Set EIF_API_KEY on the server and pass it as a Bearer token."
        )
    _log.debug("AUTH  accepted key_id=%s", info["key_id"])
    return info


def generate_key() -> str:
    """Generate a random key suitable for EIF_API_KEY."""
    return f"eif_{secrets.token_urlsafe(24)}"

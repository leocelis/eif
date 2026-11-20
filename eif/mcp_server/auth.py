"""EIF API key authentication for the self-hosted HTTP server.

Operator key: set EIF_API_KEY to any secret string and the HTTP server
requires that exact value as a Bearer token. This protects a self-hosted
EIF instance exposed beyond localhost.

Environment variables:
  EIF_API_KEY - the shared secret. If not set:
                  development: auth is bypassed (open local server)
                  production (EIF_ENV=production): ALL requests are rejected

Tenant keys (a host app serving many tenants through one server):
  EIF_TENANT_KEY_SECRET   - secret shared with the host. Not set: feature off.
  EIF_TENANT_KEY_VERSIONS - comma-separated versions accepted (default "v1")
  EIF_REVOKED_TENANTS     - comma-separated tenants whose keys are refused

  key = "eif_" + tenant + "_" + base64url_nopad(
            HMAC-SHA256(SECRET, "eif:" + VERSION + ":" + tenant))

  The tenant matches ^[a-z0-9][a-z0-9-]{0,55}$. The MAC is always 43
  characters; the tenant is the text between "eif_" and the last 44
  characters, never found by splitting on "_". Neither side stores the key.
  A tenant key resolves to key_info["tenant"]; EIF_API_KEY and the
  development keys resolve to tenant None.

  When the secret is set the tenant check runs first, and a server with the
  secret and no EIF_API_KEY serves tenant keys only, in every environment.

Security note: these are bearer tokens compared in constant time. They are
not OAuth tokens and no external validation call is made.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets

_log = logging.getLogger("eif.auth")

_API_KEY = os.environ.get("EIF_API_KEY", "")
_ENV = os.environ.get("EIF_ENV", "development")

# Dev test key - accepted in development mode only
_DEV_TEST_KEY = "dev-test-key"
_DEV_KEY_INFO = {"key_id": "dev00000", "is_dev": True, "tenant": None}

# ASGI scope entry where the HTTP middleware keeps the auth result of a request.
SCOPE_KEY = "eif.key_info"

_TENANT_PREFIX = "eif_"
_TENANT_LABEL = "eif"  # the signed text starts with the product name
_TENANT_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,55}")
_MAC_LEN = 43  # base64url without padding of a 32-byte HMAC-SHA256


class AuthError(Exception):
    pass


def _csv(name: str, default: str = "") -> list[str]:
    return [p.strip() for p in os.environ.get(name, default).split(",") if p.strip()]


def tenant_mac(secret: str, version: str, tenant: str) -> str:
    """base64url_nopad(HMAC-SHA256(secret, "eif:" + version + ":" + tenant))."""
    msg = f"{_TENANT_LABEL}:{version}:{tenant}".encode()
    digest = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def make_tenant_key(secret: str, tenant: str, version: str = "v1") -> str:
    """The key a host derives for one tenant. Raises ValueError on a bad tenant."""
    if not _TENANT_RE.fullmatch(tenant):
        raise ValueError(f"tenant {tenant!r} must match ^[a-z0-9][a-z0-9-]{{0,55}}$")
    return f"{_TENANT_PREFIX}{tenant}_{tenant_mac(secret, version, tenant)}"


def _tenant_of(api_key: str, secret: str) -> str | None:
    """The tenant a key was derived for, or None if it does not verify."""
    if len(api_key) < len(_TENANT_PREFIX) + 1 + 1 + _MAC_LEN:
        return None
    if api_key[-(_MAC_LEN + 1)] != "_":
        return None
    tenant = api_key[len(_TENANT_PREFIX):-(_MAC_LEN + 1)]
    mac = api_key[-_MAC_LEN:]
    if not _TENANT_RE.fullmatch(tenant):
        return None
    ok = False
    for version in _csv("EIF_TENANT_KEY_VERSIONS", "v1"):
        # Every version is compared, so timing does not reveal which matched.
        ok |= hmac.compare_digest(mac, tenant_mac(secret, version, tenant))
    if not ok:
        return None
    if tenant in set(_csv("EIF_REVOKED_TENANTS")):
        _log.warning("AUTH  revoked tenant key refused  tenant=%s", tenant)
        return None
    return tenant


def validate_key(api_key: str) -> dict | None:
    """Validate an API key. Returns key_info dict or None if invalid.

    key_info: {"key_id": str, "is_dev": bool, "tenant": str | None}
    """
    api_key = api_key or ""
    secret = os.environ.get("EIF_TENANT_KEY_SECRET", "")
    if secret:
        # Tenant check first: before the dev key and the open-dev shortcut.
        is_operator_key = bool(_API_KEY) and hmac.compare_digest(api_key, _API_KEY)
        if api_key.startswith(_TENANT_PREFIX) and not is_operator_key:
            tenant = _tenant_of(api_key, secret)
            if tenant is None:
                return None
            return {"key_id": f"tenant:{tenant}", "is_dev": False, "tenant": tenant}
        if not _API_KEY:
            # A tenant secret and no operator key: tenant keys only.
            return None

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
        return {"key_id": "local", "is_dev": True, "tenant": None}

    if not api_key:
        return None

    if not hmac.compare_digest(api_key, _API_KEY):
        return None

    return {"key_id": "self-host", "is_dev": False, "tenant": None}


def require_api_key(api_key: str) -> dict:
    """Validate and return key_info. Raises AuthError if invalid."""
    info = validate_key(api_key)
    if info is None:
        raise AuthError(
            "Invalid or missing API key. Send it as Authorization: Bearer <key>."
        )
    _log.debug("AUTH  accepted key_id=%s", info["key_id"])
    return info


def identity_of(key_info: dict | None) -> str | None:
    """Who a caller is, for binding an MCP session: one tenant, or the operator."""
    if not key_info:
        return None
    tenant = key_info.get("tenant")
    return f"tenant:{tenant}" if tenant else "operator"


def key_info_for_request(request) -> dict | None:
    """key_info for one HTTP request (an MCP message's own request).

    Reads the result the HTTP middleware kept on the request scope. When the
    app runs without that middleware, validates the request's Bearer header.
    Returns None when there is no request (stdio, direct calls).
    """
    if request is None:
        return None
    scope = getattr(request, "scope", None)
    if isinstance(scope, dict) and scope.get(SCOPE_KEY) is not None:
        return scope[SCOPE_KEY]
    try:
        auth = request.headers.get("authorization", "")
    except Exception:
        return None
    key = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    return validate_key(key) if key else None


def generate_key() -> str:
    """Generate a random key suitable for EIF_API_KEY."""
    return f"eif_{secrets.token_urlsafe(24)}"

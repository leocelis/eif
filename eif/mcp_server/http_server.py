"""EIF self-hosted HTTP/SSE server.

Wraps the same FastMCP app (server.py) with an ASGI HTTP+SSE transport so the
same tools are reachable over the network, not just stdio. Adds:

  - Optional Bearer-token authentication (via eif.mcp_server.auth)
  - Health/readiness endpoint at GET /health
  - POST /verify REST endpoint for the SDK interceptors

Transport: FastMCP's built-in streamable-http transport over uvicorn ASGI.

Usage (local dev):
    python -m eif.mcp_server.http_server

Usage (production):
    uvicorn eif.mcp_server.http_server:app

Environment variables:
    EIF_ENV                   = "production" | "development" (default: development)
    EIF_HOST                  = bind host (default: 127.0.0.1; set 0.0.0.0 to expose)
    EIF_PORT                  = bind port (default: 8080)
    EIF_API_KEY               = optional shared secret; if set, required as Bearer token
    EIF_RATE_LIMIT_PER_MINUTE = per-key request cap on a fixed 60s window (default: 60)
"""

from __future__ import annotations

import json
import logging
import os

_log = logging.getLogger("eif.http_server")

# ─────────────────────────────────────────────────────────────────────────────
# Import FastMCP app from server.py
# ─────────────────────────────────────────────────────────────────────────────

try:
    from mcp.server.fastmcp import FastMCP  # noqa: F401
except ImportError as exc:
    raise ImportError("pip install 'eif-engine[mcp]' to use the HTTP server") from exc

from eif.mcp_server.auth import AuthError, require_api_key  # noqa: E402
from eif.mcp_server.server import mcp  # noqa: E402  # type: ignore[attr-defined]

# ─────────────────────────────────────────────────────────────────────────────
# ASGI middleware: auth + rate limit
# ─────────────────────────────────────────────────────────────────────────────

_ENV = os.environ.get("EIF_ENV", "development")


class _RateLimiter:
    """Fixed-window per-key request counter.

    Every request costs CPU (and, on the P1 evidence path, a subprocess);
    the TOS prohibits DoS-volume usage but nothing technical enforced it.
    This is deliberately simple (in-memory, per-process, single fixed
    window) rather than a token bucket or a shared store: it is meant to
    blunt casual abuse on a single-instance deployment, not to be a
    precise or distributed rate limiter.
    """

    def __init__(self, limit_per_minute: int) -> None:
        self._limit = limit_per_minute
        self._window_start: dict[str, float] = {}
        self._count: dict[str, int] = {}

    def check(self, key: str) -> bool:
        """Return True if the request is allowed, False if over the limit."""
        import time

        now = time.monotonic()
        window = self._window_start.get(key)
        if window is None or now - window >= 60.0:
            self._window_start[key] = now
            self._count[key] = 1
            return True
        if self._count[key] >= self._limit:
            return False
        self._count[key] += 1
        return True


_rate_limiter = _RateLimiter(int(os.environ.get("EIF_RATE_LIMIT_PER_MINUTE", "60")))


class EIFMiddleware:
    """ASGI middleware that gates every MCP request behind optional auth.

    The health endpoint (/health, /readyz) is exempt - no auth required.
    The /verify REST endpoint accepts the API key in the JSON body (used by
    the SDK interceptors: EIFInterceptor, EIFCallbackHandler, eif.auto).
    In development mode (EIF_ENV=development), auth is bypassed so the
    server can be exercised locally with zero configuration.
    """

    def __init__(self, app) -> None:  # app: ASGI callable
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "websocket":
            # Same auth as HTTP: extract Bearer from headers; reject on failure.
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            ws_key = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""
            if _ENV == "development" and not ws_key:
                ws_key = "dev-test-key"
            try:
                require_api_key(ws_key)
            except AuthError:
                await send({"type": "websocket.close", "code": 4401})
                return
            if not _rate_limiter.check(ws_key):
                await send({"type": "websocket.close", "code": 4429})
                return

        if scope["type"] == "http":
            path = scope.get("path", "")

            # Health checks are always exempt
            if path in ("/health", "/readyz", "/"):
                if path in ("/health", "/readyz"):
                    await self._send_json(send, {"status": "ok", "env": _ENV}, 200)
                    return
                # Root → redirect to docs
                await self._send_json(
                    send,
                    {"name": "eif-engine", "docs": "https://github.com/leocelis/eif", "mcp": "/mcp"},
                    200,
                )
                return

            # /verify - REST endpoint for SDK interceptors (EIFInterceptor, eif.auto, EIFCallbackHandler).
            # Auth comes from the JSON body ("api_key" field), not the Authorization header.
            # This keeps the SDK integration surface as simple as possible (no extra header config).
            if path == "/verify":
                await self._handle_verify(scope, receive, send)
                return

            # Extract Bearer token from Authorization header
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            api_key = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""

            # In dev mode, accept the test key with zero configuration
            if _ENV == "development" and not api_key:
                api_key = "dev-test-key"

            try:
                require_api_key(api_key)
            except AuthError as e:
                await self._send_json(send, {"error": str(e), "code": "UNAUTHORIZED"}, 401)
                return

            if not _rate_limiter.check(api_key):
                await self._send_json(
                    send,
                    {"error": "Rate limit exceeded. Try again in a minute.", "code": "RATE_LIMITED"},
                    429,
                )
                return

        await self._app(scope, receive, send)

    async def _handle_verify(self, scope, receive, send) -> None:
        """POST /verify - REST endpoint used by SDK interceptors.

        Accepts: {"claim_text": str, "api_key": str}
        Returns: flat response compatible with sdk/interceptor.py _make_halt_record:
            {"verdict": "HALT"|"PASS", "routing": str, "evidence_summary": str,
             "confidence": float, "probe_tier": str, "evidence_source": str,
             "metric_quality": str|null}

        Auth is read from the JSON body ("api_key") rather than the Authorization
        header because the SDK interceptors call this endpoint with a one-line urllib
        call and no custom header configuration.

        """
        method = scope.get("method", "").upper()
        if method != "POST":
            await self._send_json(send, {"error": "POST required"}, 405)
            return

        # Read body (capped at 1 MiB; claims are short text)
        _MAX_BODY = 1024 * 1024
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            if len(body) > _MAX_BODY:
                await self._send_json(send, {"error": "Request body too large (max 1 MiB)"}, 413)
                return
            more_body = message.get("more_body", False)

        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            await self._send_json(send, {"error": "Invalid JSON body"}, 400)
            return

        claim_text = data.get("claim_text", "").strip()
        request_api_key = data.get("api_key", "").strip()

        if not claim_text:
            await self._send_json(send, {"error": "claim_text is required"}, 400)
            return

        # Auth: read from body api_key; dev mode accepts empty key
        if _ENV == "development" and not request_api_key:
            request_api_key = "dev-test-key"

        try:
            key_info = require_api_key(request_api_key)
        except AuthError as e:
            await self._send_json(send, {"error": str(e), "code": "UNAUTHORIZED"}, 401)
            return

        if not _rate_limiter.check(request_api_key):
            await self._send_json(
                send,
                {"error": "Rate limit exceeded. Try again in a minute.", "code": "RATE_LIMITED"},
                429,
            )
            return

        # Run the EIF pipeline
        try:
            from eif import session as session_store  # noqa: PLC0415
            from eif.mcp_server.server import (  # noqa: PLC0415
                eif_extract_claims_from_decision,
                eif_verify,
            )

            sess = await session_store.new_session()
            extracted = eif_extract_claims_from_decision(claim_text, max_claims=3)
            claims = extracted.get("claims", [])
            if not claims:
                # No structured claims extracted - treat the full text as one ASSUMED claim
                claims = [{"text": claim_text, "type": "ASSUMED", "consequence_of_wrong": "HIGH"}]

            result = await eif_verify(
                session_id=sess.session_id,
                decision=claim_text,
                claims=claims,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("/verify pipeline error: %s", exc)
            await self._send_json(
                send,
                {"error": f"EIF pipeline error: {exc}", "verdict": "PASS", "routing": "EIF_ERROR"},
                500,
            )
            return

        # Flatten eif_verify's nested response to the flat format _make_halt_record expects.
        # eif_verify returns: {verdict, halted_claims: [{claim, reason, evidence_summary,
        #   evidence_source, posterior, ...}], evidence_trails: [{claim, verdict, posterior,
        #   probe_tier, evidence_summary, evidence_source, metric_quality, ...}]}
        verdict = result.get("verdict", "PASS")
        halted: list[dict] = result.get("halted_claims", [])
        trails: list[dict] = result.get("evidence_trails", [])

        first_halt = halted[0] if halted else {}
        # Match the trail to the first halted claim for maximally relevant evidence detail
        matching_trail = next(
            (t for t in trails if t.get("claim") == first_halt.get("claim")),
            trails[0] if trails else {},
        )

        # "confidence" in HaltRecord means confidence the claim is FALSE (HALT correctness).
        # posterior is P(claim true) → confidence(HALT) = 1 - posterior.
        posterior = float(matching_trail.get("posterior") or first_halt.get("posterior") or 0.5)
        confidence = round(1.0 - posterior, 3)

        flat_response: dict = {
            "verdict": verdict,
            "routing": first_halt.get("reason", "ACT") if verdict == "HALT" else "ACT",
            "evidence_summary": (
                matching_trail.get("evidence_summary")
                or first_halt.get("evidence_summary", "")
            ),
            "confidence": confidence,
            "probe_tier": matching_trail.get("probe_tier", "NONE"),
            "evidence_source": matching_trail.get("evidence_source", ""),
            "metric_quality": matching_trail.get("metric_quality"),
        }

        _log.info(
            "/verify  key=%s  verdict=%s  tier=%s",
            key_info.get("key_id", "?")[:8],
            verdict,
            flat_response["probe_tier"],
        )
        await self._send_json(send, flat_response, 200)

    @staticmethod
    async def _send_json(send, body: dict, status: int) -> None:
        payload = json.dumps(body).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": payload, "more_body": False})


# ─────────────────────────────────────────────────────────────────────────────
# Build the ASGI app
# ─────────────────────────────────────────────────────────────────────────────

def _patch_server_session_auto_init() -> None:
    """Let clients that skip the MCP `initialize` handshake still call tools.

    Cursor's CallMcpTool opens a fresh session but does not always send the
    MCP `initialize` request before calling a tool. The mcp library enforces
    initialize -> tool-call ordering and rejects the call with -32602. If a
    non-initialize request arrives on an un-initialized session, mark the
    session initialized so the tool call proceeds. Client capabilities are
    left as None, which is safe for tool and resource calls.
    """
    try:
        from mcp.server.session import InitializationState, ServerSession
        from mcp.types import InitializeRequest as _InitReq

        _orig = ServerSession._received_request

        async def _auto_init(self, responder):  # type: ignore[override]
            if (
                self._initialization_state == InitializationState.NotInitialized
                and not isinstance(responder.request.root, _InitReq)
            ):
                self._initialization_state = InitializationState.Initialized
            await _orig(self, responder)

        ServerSession._received_request = _auto_init  # type: ignore[method-assign]
    except Exception as exc:  # noqa: BLE001
        _log.warning("auto-init patch not applied: %s", exc)


def _build_app():
    """Return the ASGI application (auth + FastMCP HTTP transports).

    Serves both transports from one process:
      /mcp                  streamable-http (current MCP spec)
      /sse + /messages      SSE (Cursor and mcp-remote proxies)

    The streamable-http transport's session manager needs its lifespan run
    to initialise its task group. Embedded as a sub-app, that lifespan does
    not fire on its own, so it is forwarded explicitly (without this, /mcp
    and /sse error out behind a proxy). This mirrors the production entry
    point used by the sibling MCP servers.
    """
    from contextlib import asynccontextmanager

    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    try:
        http_app = mcp.streamable_http_app()
    except AttributeError:
        http_app = None
    try:
        sse_app = mcp.sse_app()
    except AttributeError:
        sse_app = None

    if http_app is None and sse_app is None:
        _log.warning(
            "This mcp version exposes neither streamable_http_app() nor sse_app(). "
            "Upgrade: pip install --upgrade 'mcp>=1.4'."
        )
        return EIFMiddleware(_unavailable_app())

    _patch_server_session_auto_init()

    async def _health(_request):
        return JSONResponse({"status": "ok", "env": _ENV})

    class _Dispatcher:
        # Raw ASGI dispatch that preserves the full path. Starlette's Mount
        # strips the matched prefix, which breaks streamable-http (it expects
        # POST /mcp, not POST /).
        async def __call__(self, scope, receive, send):
            path = scope.get("path", "/")
            if sse_app is not None and (path.startswith("/sse") or path.startswith("/messages")):
                await sse_app(scope, receive, send)
                return
            await (http_app or sse_app)(scope, receive, send)

    @asynccontextmanager
    async def _lifespan(_app):
        if http_app is not None:
            async with http_app.router.lifespan_context(_app):
                yield
        else:
            yield

    inner_app = Starlette(
        lifespan=_lifespan,
        routes=[
            Route("/health", _health, methods=["GET"]),
            Route("/readyz", _health, methods=["GET"]),
            Mount("/", app=_Dispatcher()),
        ],
    )

    return EIFMiddleware(inner_app)


def _unavailable_app():
    """Last-resort app when the installed mcp version has no HTTP transport."""
    async def _app(scope, receive, send):
        if scope["type"] == "http":
            await EIFMiddleware._send_json(
                send,
                {"error": "HTTP transport unavailable. Upgrade: pip install --upgrade 'mcp>=1.4'"},
                501,
            )
    return _app


app = _build_app()


# ─────────────────────────────────────────────────────────────────────────────
# Dev server entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Start the HTTP server (dev mode, uses uvicorn)."""
    try:
        import uvicorn
    except ImportError as exc:
        raise ImportError("pip install uvicorn to run the HTTP server") from exc

    host = os.environ.get("EIF_HOST", "127.0.0.1")
    port = int(os.environ.get("EIF_PORT", "8080"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)s  %(message)s",
    )
    if host not in ("127.0.0.1", "localhost", "::1") and _ENV != "production" and not os.environ.get("EIF_API_KEY"):
        _log.warning(
            "EIF HTTP server is binding %s in development mode with no EIF_API_KEY: "
            "the server is OPEN to the network. Set EIF_ENV=production and EIF_API_KEY "
            "before exposing it.", host,
        )
    _log.info("EIF HTTP server starting - %s:%d  env=%s", host, port, _ENV)
    uvicorn.run("eif.mcp_server.http_server:app", host=host, port=port, reload=(_ENV == "development"))


if __name__ == "__main__":
    main()

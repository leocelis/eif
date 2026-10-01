"""ComplyEdge runtime checks around every EIF tool call and every /verify.

Off unless the server has COMPLYEDGE_API_KEY; the EIF engine itself never
calls out for compliance. When on, each call is checked twice through
POST /v1/check (ComplyEdge API reference):

  1. the input,  direction "prompt", before the tool runs
  2. the result, direction "output", before it is returned

A blocked check replaces the answer with the rule that fired. If ComplyEdge
cannot be reached the tool still answers: an outage of the compliance
service never breaks EIF (fail-open, logged).

Every MCP tool passes through FastMCP.call_tool, so ComplianceFastMCP
overrides that one method and covers all tools, including future ones.

Attribution (the three fields ComplyEdge writes on the audit record):
  user_id    "eifkey:<first 12 hex of sha256(caller's EIF key)>", never the
             key; "local:<login>" over stdio or an open dev server
  user_role  "mcp_client" (MCP over HTTP), "sdk_client" (/verify) or
             "maintainer" (local)
  session_id the EIF session_id when the call carries one, else the MCP
             session (Mcp-Session-Id header, or ?session_id= on SSE)

Env:
  COMPLYEDGE_API_KEY      turns the checks on (never commit it)
  COMPLYEDGE_API_URL      default https://api.complyedge.io
  COMPLYEDGE_AGENT_ID     default eif-mcp
  COMPLYEDGE_JURISDICTION default EU
  COMPLYEDGE_TIMEOUT_S    default 5
"""

from __future__ import annotations

import asyncio
import getpass
import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

MAX_TEXT = 50000  # /v1/check rejects text longer than this

_log = logging.getLogger("eif.compliance")


@dataclass
class Verdict:
    """Outcome of one check. checked=False means ComplyEdge was not consulted."""

    allowed: bool = True
    checked: bool = False
    violations: list = field(default_factory=list)
    event_id: str | None = None
    error: str | None = None


def enabled() -> bool:
    return bool(os.environ.get("COMPLYEDGE_API_KEY", "").strip())


def _local_user() -> str:
    try:
        return os.environ.get("USER") or getpass.getuser()
    except Exception:
        return "unknown"


def attribution(caller_key: str | None, role: str, session_id: str | None) -> dict:
    """user_id / user_role / session_id for the audit record. Never a credential."""
    if caller_key and caller_key != "dev-test-key":
        digest = hashlib.sha256(caller_key.encode()).hexdigest()[:12]
        ctx = {"user_id": f"eifkey:{digest}", "user_role": role}
    else:
        ctx = {"user_id": f"local:{_local_user()}", "user_role": "maintainer"}
    if session_id:
        ctx["session_id"] = session_id
    return ctx


def check(text: str, direction: str, context: dict) -> Verdict:
    """One /v1/check call. Fail-open: any transport or server error allows."""
    key = os.environ.get("COMPLYEDGE_API_KEY", "").strip()
    if not key:
        return Verdict()
    url = os.environ.get("COMPLYEDGE_API_URL", "https://api.complyedge.io").rstrip("/")
    body = json.dumps(
        {
            "text": text[:MAX_TEXT],
            "agent_id": os.environ.get("COMPLYEDGE_AGENT_ID", "eif-mcp"),
            "jurisdiction": os.environ.get("COMPLYEDGE_JURISDICTION", "EU"),
            "direction": direction,
            "context": context,
        }
    ).encode()
    req = urllib.request.Request(
        f"{url}/v1/check",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        timeout = float(os.environ.get("COMPLYEDGE_TIMEOUT_S", "5"))
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - configured https host
            data = json.loads(resp.read())
        return Verdict(
            allowed=bool(data.get("allowed", True)),
            checked=True,
            violations=data.get("violations") or [],
            event_id=data.get("event_id"),
        )
    except urllib.error.HTTPError as exc:
        return Verdict(error=f"HTTP {exc.code}")
    except Exception as exc:  # network, timeout, bad JSON
        return Verdict(error=type(exc).__name__)


async def acheck(text: str, direction: str, context: dict, what: str) -> Verdict:
    """check() off the event loop; a skipped check is logged, never raised."""
    verdict = await asyncio.to_thread(check, text, direction, context)
    if verdict.error:
        _log.warning("ComplyEdge %s check for %s skipped (%s); allowed", direction, what, verdict.error)
    return verdict


def arguments_text(tool_name: str, arguments: dict) -> str:
    return f"{tool_name} {json.dumps(arguments, default=str, sort_keys=True)}"


def blocked_payload(what: str, stage: str, verdict: Verdict) -> dict:
    """What the caller receives instead of the answer when a check blocks."""
    rules = [
        {
            "rule_id": v.get("rule_id", "rule"),
            "description": v.get("rule_description") or v.get("reason") or "",
        }
        for v in verdict.violations
    ]
    return {
        "blocked": True,
        "blocked_by": "ComplyEdge",
        "stage": stage,
        "message": f"Blocked by ComplyEdge: the {stage} of {what} failed the EU AI Act check.",
        "violations": rules,
        "audit_event_id": verdict.event_id,
    }


def _result_text(result: Any) -> str:
    """The text a client receives for a FastMCP tool result."""
    if isinstance(result, tuple):  # (content blocks, structured)
        result = result[0]
    if isinstance(result, dict):
        return json.dumps(result, default=str)
    parts = []
    for block in result or []:
        text = getattr(block, "text", None)
        parts.append(text if text is not None else str(block))
    return "\n".join(parts)


def _session_in_result(text: str) -> str | None:
    """The session_id a tool returned, if its result is a JSON object with one."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    sid = data.get("session_id") if isinstance(data, dict) else None
    return sid if isinstance(sid, str) and sid else None


def _request_identity(server: FastMCP, arguments: dict) -> tuple[str | None, str | None]:
    """(caller's bearer key, session id) for the current call; (None, ...) over stdio."""
    session = arguments.get("session_id") if isinstance(arguments.get("session_id"), str) else None
    try:
        request = server.get_context().request_context.request
    except Exception:  # no request context: direct call or stdio
        request = None
    if request is None:
        return None, session
    key = None
    try:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            key = auth.removeprefix("Bearer ").strip() or None
        if not session:
            session = request.headers.get("mcp-session-id") or None
        if not session and getattr(request, "query_params", None) is not None:
            session = request.query_params.get("session_id") or None
    except Exception:
        pass
    return key, session


class ComplianceFastMCP(FastMCP):
    """FastMCP whose single tool dispatch is screened by ComplyEdge."""

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        if not enabled():
            return await super().call_tool(name, arguments)

        key, session = _request_identity(self, arguments)
        ctx = attribution(key, "mcp_client", session)

        verdict = await acheck(arguments_text(name, arguments), "prompt", ctx, name)
        if not verdict.allowed:
            return [TextContent(type="text", text=json.dumps(blocked_payload(name, "input", verdict), indent=2))]

        result = await super().call_tool(name, arguments)
        text = _result_text(result)

        # A call made before any session exists (eif_new_session) gets its
        # session from the result, so its output record links to the calls
        # that follow. The input record keeps none: no session existed yet.
        if "session_id" not in ctx:
            created = _session_in_result(text)
            if created:
                ctx = {**ctx, "session_id": created}

        verdict = await acheck(text, "output", ctx, name)
        if not verdict.allowed:
            return [TextContent(type="text", text=json.dumps(blocked_payload(name, "output", verdict), indent=2))]
        return result

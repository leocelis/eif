"""Every EIF tool call and every /verify goes through ComplyEdge when the
server has a key.

Before this, no EIF MCP tool and not the /verify endpoint called ComplyEdge:
the public enforcement seal counted only the CI probe. ComplianceFastMCP
overrides FastMCP.call_tool, the one dispatch all 25 tools pass through, and
/verify checks the claim text and the verdict. These tests run the real
dispatch and the real endpoint against a local stub of POST /v1/check.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from eif.mcp_server import compliance
from eif.mcp_server import server as eif_server
from eif.mcp_server.server import mcp

KEY = "ce_test_key_for_stub"


@pytest.fixture
def stub(monkeypatch):
    """A fake ComplyEdge. `answers` is popped per call; default allows."""
    state = {"seen": [], "auth": [], "answers": [], "status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["seen"].append(body)
            state["auth"].append(self.headers.get("Authorization"))
            answer = state["answers"].pop(0) if state["answers"] else {"allowed": True, "violations": []}
            out = json.dumps({"event_id": f"evt-{len(state['seen'])}", "latency_ms": 1, **answer}).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("COMPLYEDGE_API_KEY", KEY)
    monkeypatch.setenv("COMPLYEDGE_API_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.delenv("COMPLYEDGE_AGENT_ID", raising=False)
    monkeypatch.delenv("COMPLYEDGE_JURISDICTION", raising=False)
    yield state
    server.shutdown()


@pytest.fixture
def probe_tool():
    """A throwaway tool registered on the real app; records whether it ran."""
    calls = []

    def ce_probe_tool(q: str = "") -> dict:
        calls.append(q)
        return {"echo": q}

    mcp.add_tool(ce_probe_tool, name="ce_probe_tool")
    yield calls
    mcp._tool_manager._tools.pop("ce_probe_tool", None)


def _remote(monkeypatch, headers=None, query=None):
    """Make the real get_context() look like an HTTP request (Starlette-like)."""
    request = SimpleNamespace(headers=headers or {}, query_params=query or {})
    ctx = SimpleNamespace(request_context=SimpleNamespace(request=request))
    monkeypatch.setattr(mcp, "get_context", lambda: ctx)


def _text(result) -> str:
    return "\n".join(block.text for block in result)


def _block(rule="EU-AI-ACT-ART5-TEST"):
    return {"allowed": False, "violations": [{"rule_id": rule, "rule_description": "test rule"}]}


def test_real_tool_is_checked_on_the_way_in_and_out(stub):
    result = asyncio.run(mcp.call_tool("eif_new_session", {}))

    assert len(stub["seen"]) == 2
    prompt, output = stub["seen"]
    assert prompt["direction"] == "prompt"
    assert prompt["text"] == "eif_new_session {}"
    assert output["direction"] == "output"
    assert output["text"] == _text(result)
    assert "session_id" in json.loads(_text(result))
    for body in stub["seen"]:
        assert body["agent_id"] == "eif-mcp"
        assert body["jurisdiction"] == "EU"
        assert body["context"]["user_role"] == "maintainer"
        assert body["context"]["user_id"].startswith("local:")
    assert stub["auth"] == [f"Bearer {KEY}"] * 2
    assert KEY not in json.dumps(stub["seen"])


def test_remote_caller_is_a_hash_never_the_key(stub, monkeypatch):
    eif_key = "eif_live_secret_abcdef123456"
    _remote(monkeypatch, headers={"authorization": f"Bearer {eif_key}", "mcp-session-id": "mcp-sess-7"})
    created = json.loads(_text(asyncio.run(mcp.call_tool("eif_new_session", {}))))
    asyncio.run(mcp.call_tool("eif_get_session", {"session_id": created["session_id"]}))

    digest = hashlib.sha256(eif_key.encode()).hexdigest()[:12]
    ctxs = [b["context"] for b in stub["seen"]]
    assert len(ctxs) == 4
    assert all(c["user_id"] == f"eifkey:{digest}" for c in ctxs)
    assert all(c["user_role"] == "mcp_client" for c in ctxs)
    # No EIF session yet -> the MCP session; once the call names one, that one.
    assert [c["session_id"] for c in ctxs] == ["mcp-sess-7", "mcp-sess-7", created["session_id"], created["session_id"]]
    dumped = json.dumps(stub["seen"])
    assert eif_key not in dumped and KEY not in dumped


def test_sse_session_query_is_used(stub, monkeypatch):
    _remote(monkeypatch, headers={"authorization": "Bearer k"}, query={"session_id": "sse-9"})
    asyncio.run(mcp.call_tool("eif_new_session", {}))
    assert stub["seen"][0]["context"]["session_id"] == "sse-9"


def test_blocked_input_never_runs_the_tool(stub, probe_tool):
    stub["answers"] = [_block()]
    out = json.loads(_text(asyncio.run(mcp.call_tool("ce_probe_tool", {"q": "hello"}))))

    assert probe_tool == []
    assert out["blocked"] is True and out["stage"] == "input"
    assert out["violations"][0]["rule_id"] == "EU-AI-ACT-ART5-TEST"
    assert out["audit_event_id"] == "evt-1"
    assert len(stub["seen"]) == 1


def test_blocked_output_is_not_returned(stub, probe_tool):
    stub["answers"] = [{"allowed": True, "violations": []}, _block("EU-OUT-1")]
    out = _text(asyncio.run(mcp.call_tool("ce_probe_tool", {"q": "secret-answer"})))

    assert probe_tool == ["secret-answer"]
    assert "secret-answer" not in out
    data = json.loads(out)
    assert data["stage"] == "output" and data["violations"][0]["rule_id"] == "EU-OUT-1"


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_unreachable_complyedge_fails_open(monkeypatch, probe_tool):
    monkeypatch.setenv("COMPLYEDGE_API_KEY", KEY)
    monkeypatch.setenv("COMPLYEDGE_API_URL", f"http://127.0.0.1:{_closed_port()}")
    out = json.loads(_text(asyncio.run(mcp.call_tool("ce_probe_tool", {"q": "x"}))))
    assert out == {"echo": "x"}
    assert probe_tool == ["x"]


def test_server_error_fails_open(stub, probe_tool):
    stub["status"] = 500
    out = json.loads(_text(asyncio.run(mcp.call_tool("ce_probe_tool", {"q": "y"}))))
    assert out == {"echo": "y"}
    assert len(stub["seen"]) == 2


def test_no_key_means_no_checks(stub, monkeypatch, probe_tool):
    monkeypatch.delenv("COMPLYEDGE_API_KEY")
    out = json.loads(_text(asyncio.run(mcp.call_tool("ce_probe_tool", {"q": "z"}))))
    assert out == {"echo": "z"}
    assert stub["seen"] == []


def test_every_registered_tool_uses_the_screened_dispatch():
    # The low-level server holds the bound call_tool captured at construction;
    # it must be ComplianceFastMCP's, or no tool is screened.
    assert isinstance(mcp, compliance.ComplianceFastMCP)
    handler = type(mcp).call_tool
    assert handler is compliance.ComplianceFastMCP.call_tool


# ── /verify (SDK interceptors) ───────────────────────────────────────────────


@pytest.fixture
def verify_client(monkeypatch):
    from starlette.testclient import TestClient

    from eif.mcp_server import http_server

    ran = []

    def fake_extract(text, max_claims=3):
        return {"claims": [{"text": text, "type": "ASSUMED", "consequence_of_wrong": "HIGH"}]}

    async def fake_verify(session_id, decision, claims):
        ran.append(decision)
        return {"verdict": "PASS", "halted_claims": [], "evidence_trails": [{"claim": decision, "posterior": 0.9}]}

    monkeypatch.setattr(eif_server, "eif_extract_claims_from_decision", fake_extract)
    monkeypatch.setattr(eif_server, "eif_verify", fake_verify)
    monkeypatch.setattr(http_server, "_rate_limiter", http_server._RateLimiter(1000))
    return TestClient(http_server.app), ran


def test_verify_is_checked_in_and_out(stub, verify_client):
    client, ran = verify_client
    sdk_key = "eif_sdk_key_0123456789"
    r = client.post("/verify", json={"claim_text": "Revenue grew 40% because of the launch", "api_key": sdk_key})

    assert r.status_code == 200 and r.json()["verdict"] == "PASS"
    assert ran == ["Revenue grew 40% because of the launch"]
    prompt, output = stub["seen"]
    assert prompt["direction"] == "prompt" and prompt["text"] == "Revenue grew 40% because of the launch"
    assert output["direction"] == "output" and json.loads(output["text"]) == r.json()
    digest = hashlib.sha256(sdk_key.encode()).hexdigest()[:12]
    for body in stub["seen"]:
        assert body["context"]["user_id"] == f"eifkey:{digest}"
        assert body["context"]["user_role"] == "sdk_client"
        assert body["context"]["session_id"]
    assert sdk_key not in json.dumps(stub["seen"])


def test_verify_blocked_input_halts_without_running_the_pipeline(stub, verify_client):
    client, ran = verify_client
    stub["answers"] = [_block()]
    r = client.post("/verify", json={"claim_text": "bad text", "api_key": "k"})

    body = r.json()
    assert r.status_code == 200
    assert body["verdict"] == "HALT" and body["routing"] == "COMPLYEDGE_BLOCKED"
    assert body["compliance"]["violations"][0]["rule_id"] == "EU-AI-ACT-ART5-TEST"
    assert ran == []
    assert len(stub["seen"]) == 1


def test_verify_blocked_output_halts(stub, verify_client):
    client, _ = verify_client
    stub["answers"] = [{"allowed": True, "violations": []}, _block("EU-OUT-2")]
    body = client.post("/verify", json={"claim_text": "fine text", "api_key": "k"}).json()
    assert body["verdict"] == "HALT" and body["compliance"]["stage"] == "output"


def test_verify_without_key_makes_no_checks(stub, verify_client, monkeypatch):
    monkeypatch.delenv("COMPLYEDGE_API_KEY")
    client, ran = verify_client
    r = client.post("/verify", json={"claim_text": "fine text", "api_key": "k"})
    assert r.json()["verdict"] == "PASS"
    assert stub["seen"] == [] and ran == ["fine text"]

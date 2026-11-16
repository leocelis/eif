"""Host-derived tenant keys, session owners and the tenant tool allowlist.

Spec: docs/eif_host_tenant_keys_tech_spec.md (section 5 lists these tests).
No network: web search and model calls are never reached (stubbed or refused
before evidence collection).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from eif import session as session_store
from eif.mcp_server import auth
from eif.mcp_server import server as eif_server

SECRET = "test-secret-do-not-use"
VECTOR = "eif_acme_Zz3YW-iyGIXp3c4AL9D0Kcpxxyneizso6QEKw0_Lf9I"
OPERATOR = "operator-key-0123456789"


def _tamper(key: str) -> str:
    return key[:-1] + ("A" if key[-1] != "A" else "B")


@pytest.fixture
def tenant_env(monkeypatch):
    monkeypatch.setenv("EIF_TENANT_KEY_SECRET", SECRET)
    monkeypatch.delenv("EIF_TENANT_KEY_VERSIONS", raising=False)
    monkeypatch.delenv("EIF_REVOKED_TENANTS", raising=False)
    monkeypatch.setattr(auth, "_API_KEY", "")
    monkeypatch.setattr(auth, "_ENV", "development")


# ── E1: the key ───────────────────────────────────────────────────────────────


def test_vector_is_reproduced_byte_for_byte():
    assert auth.make_tenant_key(SECRET, "acme", "v1") == VECTOR
    assert len(VECTOR) - len("eif_acme_") == 43 and VECTOR[-44] == "_"


def test_vector_verifies(tenant_env):
    info = auth.validate_key(VECTOR)
    assert info == {"key_id": "tenant:acme", "is_dev": False, "tenant": "acme"}


def test_tampered_mac_is_refused(tenant_env):
    assert auth.validate_key(_tamper(VECTOR)) is None


def test_unknown_version_is_refused(tenant_env):
    v2 = auth.make_tenant_key(SECRET, "acme", "v2")
    assert auth.validate_key(v2) is None


def test_added_version_is_accepted(tenant_env, monkeypatch):
    monkeypatch.setenv("EIF_TENANT_KEY_VERSIONS", "v1, v2")
    assert auth.validate_key(auth.make_tenant_key(SECRET, "acme", "v2"))["tenant"] == "acme"
    assert auth.validate_key(VECTOR)["tenant"] == "acme"


def test_revoked_tenant_is_refused(tenant_env, monkeypatch):
    monkeypatch.setenv("EIF_REVOKED_TENANTS", "other,acme")
    assert auth.validate_key(VECTOR) is None


@pytest.mark.parametrize("bad", ["Acme", "-acme", "ac_me", "a" * 57, ""])
def test_tenant_that_breaks_the_rule_is_refused(tenant_env, bad):
    forged = f"eif_{bad}_{auth.tenant_mac(SECRET, 'v1', bad)}"
    assert auth.validate_key(forged) is None
    if bad:
        with pytest.raises(ValueError):
            auth.make_tenant_key(SECRET, bad)


def test_tenant_with_underscore_in_mac_is_parsed_from_the_end(tenant_env):
    # The MAC may contain "_" and "-"; the tenant is never found by splitting.
    for tenant in ("a", "acme-corp", "x" * 56, "0-0"):
        assert auth.validate_key(auth.make_tenant_key(SECRET, tenant))["tenant"] == tenant


def test_key_from_another_secret_is_refused(tenant_env):
    assert auth.validate_key(auth.make_tenant_key("other-secret", "acme")) is None


@pytest.mark.parametrize("env", ["development", "production"])
def test_secret_without_operator_key_serves_tenant_keys_only(tenant_env, monkeypatch, env):
    monkeypatch.setattr(auth, "_ENV", env)
    assert auth.validate_key(VECTOR)["tenant"] == "acme"
    assert auth.validate_key(_tamper(VECTOR)) is None
    # The open-dev shortcut and the dev test key are off.
    assert auth.validate_key("anything") is None
    assert auth.validate_key("dev-test-key") is None
    assert auth.validate_key("") is None


# ── EIF_API_KEY behaves as before ─────────────────────────────────────────────


def test_operator_key_unchanged_without_secret(monkeypatch):
    monkeypatch.delenv("EIF_TENANT_KEY_SECRET", raising=False)
    monkeypatch.setattr(auth, "_API_KEY", OPERATOR)
    monkeypatch.setattr(auth, "_ENV", "production")
    assert auth.validate_key(OPERATOR) == {"key_id": "self-host", "is_dev": False, "tenant": None}
    assert auth.validate_key("wrong") is None
    assert auth.validate_key(VECTOR) is None  # no secret: a tenant key is just a wrong key
    assert auth.validate_key("dev-test-key") is None


def test_open_dev_and_closed_prod_unchanged_without_secret(monkeypatch):
    monkeypatch.delenv("EIF_TENANT_KEY_SECRET", raising=False)
    monkeypatch.setattr(auth, "_API_KEY", "")
    monkeypatch.setattr(auth, "_ENV", "development")
    assert auth.validate_key("anything")["key_id"] == "local"
    assert auth.validate_key("dev-test-key")["key_id"] == "dev00000"
    monkeypatch.setattr(auth, "_ENV", "production")
    assert auth.validate_key("anything") is None


def test_operator_key_with_eif_prefix_still_works_next_to_tenant_keys(tenant_env, monkeypatch):
    generated = auth.generate_key()  # starts with "eif_"
    monkeypatch.setattr(auth, "_API_KEY", generated)
    assert auth.validate_key(generated)["tenant"] is None
    assert auth.validate_key(generated)["key_id"] == "self-host"
    assert auth.validate_key(VECTOR)["tenant"] == "acme"
    assert auth.validate_key("dev-test-key")["key_id"] == "dev00000"  # unchanged with an operator key


# ── E2: session owners ────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


def test_other_tenant_gets_not_found_by_store():
    async def go():
        a = await session_store.new_session(tenant="acme")
        assert (await session_store.get_session(a.session_id, tenant="acme")).session_id == a.session_id
        with pytest.raises(ValueError, match="not found or expired"):
            await session_store.get_session(a.session_id, tenant="beta")
        with pytest.raises(ValueError, match="not found or expired"):
            await session_store.update_session(a.session_id, tenant="beta", last_registry={})
        # same wording as an id that does not exist
        with pytest.raises(ValueError) as real:
            await session_store.get_session(a.session_id, tenant="beta")
        with pytest.raises(ValueError) as fake:
            await session_store.get_session("no-such-id", tenant="beta")
        assert str(real.value).replace(a.session_id, "X") == str(fake.value).replace("no-such-id", "X")

    _run(go())


def test_operator_and_tenant_sessions_do_not_cross():
    async def go():
        op = await session_store.new_session(tenant=None)
        ten = await session_store.new_session(tenant="acme")
        with pytest.raises(ValueError, match="not found or expired"):
            await session_store.get_session(op.session_id, tenant="acme")
        with pytest.raises(ValueError, match="not found or expired"):
            await session_store.get_session(ten.session_id, tenant=None)
        assert (await session_store.get_session(op.session_id)).session_id == op.session_id

    _run(go())


def test_caller_scope_is_the_default_owner_and_reader():
    async def go():
        with session_store.caller_scope("acme"):
            s = await session_store.new_session()
            await session_store.update_session(s.session_id, last_registry={"x": 1})
        assert session_store.owner_of(s.session_id) == "acme"
        with session_store.caller_scope("beta"), pytest.raises(ValueError, match="not found or expired"):
            await session_store.get_session(s.session_id)

    _run(go())


def test_complyedge_note_never_writes_another_tenants_session():
    async def go():
        s = await session_store.new_session(tenant="acme")
        await session_store.note_complyedge_event(s.session_id, {"event_id": "e1"}, tenant="beta")
        got = await session_store.get_session(s.session_id, tenant="acme")
        assert got.complyedge_event_ids == []

    _run(go())


@pytest.mark.parametrize("kind", ["summary", "registry", "provenance", "programme", "calibration"])
def test_other_tenant_gets_not_found_by_resource(kind):
    async def go():
        s = await session_store.new_session(tenant="acme")
        uri = f"eif://session/{s.session_id}/{kind}"
        with session_store.caller_scope("beta"):
            contents = list(await eif_server.mcp.read_resource(uri))
        body = json.loads(contents[0].content)
        assert "not found or expired" in body["error"]
        with session_store.caller_scope("acme"):
            contents = list(await eif_server.mcp.read_resource(uri))
        body = json.loads(contents[0].content)
        assert not (isinstance(body, dict) and "not found" in str(body.get("error", "")))

    _run(go())


# ── MCP over HTTP: tool allowlist, per-message tenant, session binding ────────

_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


@pytest.fixture(scope="module")
def mcp_client():
    from starlette.testclient import TestClient

    from eif.mcp_server import http_server

    http_server._rate_limiter = http_server._RateLimiter(10000)
    # The streamable-http session manager runs once per process: one client.
    with TestClient(http_server.app, base_url="http://127.0.0.1:8080") as client:
        yield client


def _rpc(client, key, method, params=None, session=None, rid=1):
    headers = {**_HEADERS, "authorization": f"Bearer {key}"}
    if session:
        headers["mcp-session-id"] = session
    body = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
    r = client.post("/mcp", headers=headers, json=body)
    payload = None
    for line in r.text.splitlines():
        if line.startswith("data:"):
            payload = json.loads(line[5:].strip())
    if payload is None and r.headers.get("content-type", "").startswith("application/json"):
        payload = r.json()
    return r, payload


def _open(client, key):
    r, msg = _rpc(client, key, "initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    })
    assert r.status_code == 200, r.text
    sid = r.headers["mcp-session-id"]
    client.post("/mcp", headers={**_HEADERS, "authorization": f"Bearer {key}", "mcp-session-id": sid},
                json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return sid


def _tool(client, key, sid, name, args, rid=2):
    _, msg = _rpc(client, key, "tools/call", {"name": name, "arguments": args}, session=sid, rid=rid)
    return msg


def _tool_json(msg):
    return json.loads(msg["result"]["content"][0]["text"])


def test_tenant_tools_list_shows_three_and_challenge_is_refused(tenant_env, monkeypatch, mcp_client):
    monkeypatch.setattr(auth, "_API_KEY", OPERATOR)
    sid = _open(mcp_client, VECTOR)
    _, listed = _rpc(mcp_client, VECTOR, "tools/list", session=sid, rid=3)
    names = sorted(t["name"] for t in listed["result"]["tools"])
    assert names == sorted(eif_server.TENANT_TOOLS)

    refused = _tool(mcp_client, VECTOR, sid, "eif_challenge", {"session_id": "x", "claim": "y"})
    assert "error" in refused and "not available to tenant keys" in refused["error"]["message"]

    # The operator key on its own MCP session still sees every tool.
    op_sid = _open(mcp_client, OPERATOR)
    _, op_listed = _rpc(mcp_client, OPERATOR, "tools/list", session=op_sid, rid=4)
    assert len(op_listed["result"]["tools"]) > 3


def test_tenant_session_is_owned_and_hidden_from_other_tenants(tenant_env, monkeypatch, mcp_client):
    import eif.falsify.evidence_collector as ec

    def _no_network(*a, **k):
        raise AssertionError("evidence collection must not run for a foreign session")

    monkeypatch.setattr(ec, "collect_evidence", _no_network)
    beta = auth.make_tenant_key(SECRET, "beta")

    a_sid = _open(mcp_client, VECTOR)
    created = _tool_json(_tool(mcp_client, VECTOR, a_sid, "eif_new_session", {}))
    eif_session = created["session_id"]
    assert session_store.owner_of(eif_session) == "acme"

    b_sid = _open(mcp_client, beta)
    msg = _tool(mcp_client, beta, b_sid, "eif_verify", {
        "session_id": eif_session, "decision": "d",
        "claims": [{"text": "c", "claim_type": "ASSUMED"}],
    })
    assert msg["result"]["isError"] is True
    assert "not found or expired" in msg["result"]["content"][0]["text"]

    _, res = _rpc(mcp_client, beta, "resources/read",
                  {"uri": f"eif://session/{eif_session}/summary"}, session=b_sid, rid=5)
    assert "not found or expired" in json.loads(res["result"]["contents"][0]["text"])["error"]


def test_mcp_session_opened_with_one_key_and_continued_with_another_is_refused(
    tenant_env, monkeypatch, mcp_client
):
    monkeypatch.setattr(auth, "_API_KEY", OPERATOR)
    beta = auth.make_tenant_key(SECRET, "beta")
    sid = _open(mcp_client, VECTOR)

    for other in (beta, OPERATOR):
        _, msg = _rpc(mcp_client, other, "tools/list", session=sid, rid=6)
        assert "error" in msg and "different key" in msg["error"]["message"]
        msg = _tool(mcp_client, other, sid, "eif_new_session", {}, rid=7)
        assert "error" in msg and "different key" in msg["error"]["message"]

    # The opener can still use it.
    _, ok = _rpc(mcp_client, VECTOR, "tools/list", session=sid, rid=8)
    assert "result" in ok


def test_tampered_key_gets_401_over_http(tenant_env, mcp_client):
    r, _ = _rpc(mcp_client, _tamper(VECTOR), "tools/list")
    assert r.status_code == 401


# ── POST /verify ──────────────────────────────────────────────────────────────


def test_verify_endpoint_creates_a_session_owned_by_the_tenant(tenant_env, monkeypatch, mcp_client):
    monkeypatch.delenv("COMPLYEDGE_API_KEY", raising=False)
    seen = {}

    def fake_extract(text, max_claims=3):
        return {"claims": [{"text": text, "type": "ASSUMED", "consequence_of_wrong": "HIGH"}]}

    async def fake_verify(session_id, decision, claims):
        seen["owner"] = session_store.owner_of(session_id)
        seen["caller"] = session_store.caller_tenant.get()
        await session_store.get_session(session_id)  # readable as the caller
        return {"verdict": "PASS", "halted_claims": [], "evidence_trails": []}

    monkeypatch.setattr(eif_server, "eif_extract_claims_from_decision", fake_extract)
    monkeypatch.setattr(eif_server, "eif_verify", fake_verify)

    r = mcp_client.post("/verify", json={"claim_text": "Revenue grew 40%", "api_key": VECTOR})
    assert r.status_code == 200 and r.json()["verdict"] == "PASS"
    assert seen == {"owner": "acme", "caller": "acme"}

    r = mcp_client.post("/verify", json={"claim_text": "x", "api_key": _tamper(VECTOR)})
    assert r.status_code == 401

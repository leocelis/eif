"""eif_verify must not answer PASS when no evidence was found.

Found in a 2026-11 audit: on a plain install (no host_tool_outputs, no ddgs),
every claim came back INSUFFICIENT at the prior (0.5) and eif_verify returned
PASS, which callers read as "verified, proceed". The engine's own thresholds
(THRESHOLD_ACT = 0.70) say a claim below 0.70 is not ready to act on, so the
verdict is REVISE. Evidence that supports the claim still gives PASS.
"""

import pytest

from eif import session as session_store
from eif.mcp_server import server as server_mod
from eif.mcp_server.server import eif_verify

EVIDENCE = "Portfolio database (latest sync): position NVDA holds 250 shares."
CLAIM = {
    "text": "The portfolio holds 250 shares of NVDA",
    "claim_type": "ASSUMED",
    "consequence_of_wrong": "MEDIUM",
}


@pytest.fixture(autouse=True)
def _no_web_search(monkeypatch):
    # Keep the test offline and deterministic even where ddgs is installed.
    import eif.falsify.native_tools as nt

    monkeypatch.setattr(nt, "get_native_search_fn", lambda: None, raising=False)
    yield


@pytest.mark.asyncio
async def test_no_evidence_returns_revise_not_pass():
    sess = await session_store.new_session()
    result = await eif_verify(
        session_id=sess.session_id,
        decision="Rebalance assuming the NVDA position size",
        claims=[CLAIM],
    )
    assert result["verdict"] == "REVISE", result.get("next_step")
    assert all(t["posterior"] < server_mod.THRESHOLD_ACT for t in result["evidence_trails"])
    assert "host_tool_outputs" in result["next_step"]


@pytest.mark.asyncio
async def test_supporting_host_data_still_passes():
    sess = await session_store.new_session()
    result = await eif_verify(
        session_id=sess.session_id,
        decision="Rebalance assuming the NVDA position size",
        claims=[CLAIM],
        host_tool_outputs=[{
            "tool_name": "portfolio_db",
            "query": "portfolio quantity shares held NVDA position",
            "result": EVIDENCE,
            "data_scope": "INTERNAL",
        }],
    )
    assert result["verdict"] == "PASS"

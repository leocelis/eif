"""P0 host-tool numeric comparison + advisory routing regression tests.

Both behaviors were found while dogfooding P0 passive mode against a real
external data source:
  1. The P0 verdict was keyword-overlap only, so a claim that exactly matched
     the evidence number still read as CONTRADICTS.
  2. HIGH_RISK_ASSUMED advisory entries (documented as non-blocking) drove
     the overall verdict to HALT.
"""

import pytest

from eif import session as session_store
from eif.falsify.evidence_collector import (
    HostTool,
    HostToolRegistry,
    _extract_numbers,
    _numbers_match,
    collect_from_host_tools,
)
from eif.mcp_server.server import eif_verify

EVIDENCE = "Portfolio database (latest sync): position NVDA holds 250 shares."


def _registry() -> HostToolRegistry:
    return HostToolRegistry([
        HostTool(
            name="portfolio_db",
            description="Portfolio positions database",
            capability_keywords=["portfolio", "shares", "position", "nvda"],
            fn=lambda _q: EVIDENCE,
            data_scope="INTERNAL",
        )
    ])


class TestNumericFastPath:
    def test_matching_number_supports(self):
        res = collect_from_host_tools(
            "The portfolio holds 250 shares of NVDA",
            "portfolio position count differs from 250 shares",
            _registry(),
        )
        assert res.verdict == "SUPPORTS"
        assert res.probe_tier == "P0_HOST_TOOL"

    def test_mismatching_number_contradicts(self):
        res = collect_from_host_tools(
            "The portfolio holds 10,000 shares of NVDA",
            "portfolio position count differs from 10,000 shares",
            _registry(),
        )
        assert res.verdict == "CONTRADICTS"

    def test_extract_numbers_strips_commas_and_years(self):
        assert 10000.0 in _extract_numbers("holds 10,000 shares")
        assert 2024.0 not in _extract_numbers("synced in 2024")
        assert 3.5 in _extract_numbers("rate of 3.5 percent")

    def test_numbers_match_tolerance(self):
        assert _numbers_match(250.0, 250.0)
        assert _numbers_match(100.0, 101.0)  # within 2%
        assert not _numbers_match(250.0, 10000.0)


class TestAdvisoryDoesNotBlock:
    @pytest.mark.asyncio
    async def test_high_risk_assumed_with_supporting_p0_passes(self):
        sess = await session_store.new_session()
        result = await eif_verify(
            session_id=sess.session_id,
            decision="Rebalance assuming the NVDA position size",
            claims=[{
                "text": "The portfolio holds 250 shares of NVDA",
                "claim_type": "ASSUMED",
                "consequence_of_wrong": "HIGH",
            }],
            host_tool_outputs=[{
                "tool_name": "portfolio_db",
                "query": "portfolio quantity shares held NVDA position",
                "result": EVIDENCE,
                "data_scope": "INTERNAL",
            }],
        )
        assert result["verdict"] == "PASS"
        advisories = [e for e in result["halted_claims"] if e.get("advisory")]
        assert advisories, "the HIGH_RISK_ASSUMED review flag must still be surfaced"

    @pytest.mark.asyncio
    async def test_contradicted_claim_still_halts(self):
        sess = await session_store.new_session()
        result = await eif_verify(
            session_id=sess.session_id,
            decision="Rebalance assuming the NVDA position size",
            claims=[{
                "text": "The portfolio holds 10,000 shares of NVDA",
                "claim_type": "ASSUMED",
                "consequence_of_wrong": "HIGH",
            }],
            host_tool_outputs=[{
                "tool_name": "portfolio_db",
                "query": "portfolio quantity shares held NVDA position",
                "result": EVIDENCE,
                "data_scope": "INTERNAL",
            }],
        )
        assert result["verdict"] == "HALT"
        blocking = [e for e in result["halted_claims"] if not e.get("advisory")]
        assert blocking and "CONTRADICTS" in blocking[0]["reason"]

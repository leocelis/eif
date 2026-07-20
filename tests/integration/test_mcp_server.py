"""Integration tests for the MCP tool layer.

Smoke + key-contract coverage for the 25 tools exposed by
[eif/mcp_server/server.py](eif/mcp_server/server.py). Each test invokes a
tool with minimal valid inputs and asserts that the return shape contains
the top-level keys the tool's description documents.

These tests do NOT require network access or API keys. Tools that have
optional LLM-driven paths (causal_gate CEP, multi-critic challenge) are
exercised via their documented no-API-key fallbacks. Cross-tool joins
(claim_text, record_id) are kept inside a single session where needed.
"""

from __future__ import annotations

import pytest

from eif import session as session_store
from eif.mcp_server.server import (
    eif_calibrate,
    eif_calibration_report,
    eif_catch_rate_report,
    eif_causal_gate,
    eif_challenge,
    eif_check_rules_installed,
    eif_compliance_report,
    eif_declare,
    eif_demo,
    eif_explain,
    eif_extract_claims_from_decision,
    eif_falsify,
    eif_get_context,
    eif_get_session,
    eif_hypothesis_agenda,
    eif_input_guard,
    eif_new_session,
    eif_programme_health,
    eif_provenance,
    eif_record,
    eif_record_outcome,
    eif_replicate,
    eif_sycophancy_gate,
    eif_update,
    eif_verify,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _new_session_id() -> str:
    result = await eif_new_session()
    return result["session_id"]


def _claim(text: str, claim_type: str = "ASSUMED", consequence: str = "HIGH") -> dict:
    return {
        "text": text,
        "claim_type": claim_type,
        "consequence_of_wrong": consequence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sync tools
# ─────────────────────────────────────────────────────────────────────────────


class TestSyncTools:
    """Tools that don't need a session or async context."""

    def test_get_context_returns_phases_rules_quick_reference(self):
        result = eif_get_context()
        assert isinstance(result, dict)
        assert "phases" in result
        assert "rules" in result
        assert "quick_reference" in result
        assert isinstance(result["phases"], list) and len(result["phases"]) > 0
        for phase in result["phases"]:
            # R24-01: phase shape = {id, description, trigger, output}
            assert "id" in phase
            assert "description" in phase

    def test_get_context_topic_filter(self):
        result = eif_get_context(topic="DECLARE")
        assert isinstance(result, dict)
        assert "phases" in result

    def test_check_rules_installed_default_paths(self):
        # Default heuristic - CWD-relative; may return False, but must not crash.
        result = eif_check_rules_installed()
        assert isinstance(result, dict)
        assert "installed" in result
        assert "checked_files" in result

    def test_check_rules_installed_explicit_paths(self):
        result = eif_check_rules_installed(file_paths=["/nonexistent/CLAUDE.md"])
        assert isinstance(result, dict)
        assert result["installed"] is False

    def test_extract_claims_from_decision(self):
        result = eif_extract_claims_from_decision(
            "Commission a 10-article series on Hollow Ascent. "
            "It has 5,000+ IGDB hype followers."
        )
        assert isinstance(result, dict)
        assert "claims" in result
        assert "total_extracted" in result
        assert "next_step" in result
        assert isinstance(result["claims"], list)
        assert 2 <= len(result["claims"]) <= 4
        for c in result["claims"]:
            assert "text" in c
            assert "claim_type" in c
            assert "consequence_of_wrong" in c
            assert "halt_probability" in c

    def test_extract_claims_from_decision_rejects_empty(self):
        with pytest.raises(ValueError):
            eif_extract_claims_from_decision("")


# ─────────────────────────────────────────────────────────────────────────────
# Session tool
# ─────────────────────────────────────────────────────────────────────────────


class TestNewSessionTool:
    """eif_new_session is the required first call - every other stateful tool
    depends on the session_id it returns."""

    @pytest.mark.asyncio
    async def test_new_session_returns_usable_session_id(self):
        result = await eif_new_session()
        assert isinstance(result, dict)
        assert "session_id" in result and result["session_id"]
        # Round-trip: the id must work immediately on another tool.
        sess_overview = await eif_get_session(session_id=result["session_id"])
        assert sess_overview["session_id"] == result["session_id"]

    @pytest.mark.asyncio
    async def test_new_session_ids_are_unique(self):
        a = await eif_new_session()
        b = await eif_new_session()
        assert a["session_id"] != b["session_id"]

    @pytest.mark.asyncio
    async def test_unknown_session_id_error_points_to_new_session(self):
        with pytest.raises(ValueError, match="eif_new_session"):
            await eif_get_session(session_id="does-not-exist")


# ─────────────────────────────────────────────────────────────────────────────
# Core pipeline async tools
# ─────────────────────────────────────────────────────────────────────────────


class TestCorePipeline:
    """The 8 ADVANCED granular pipeline tools."""

    @pytest.mark.asyncio
    async def test_declare_returns_registry_and_high_risk(self):
        sid = await _new_session_id()
        result = await eif_declare(
            session_id=sid,
            decision="Deploy v2 to production",
            claims=[
                _claim("Latency stays under 100ms"),
                _claim("Database supports 10k writes/sec", "GUESSED"),
            ],
        )
        assert isinstance(result, dict)
        assert "registry" in result
        assert "high_risk_claims" in result
        assert "harking_detected" in result
        assert "falsification_required" in result

    @pytest.mark.asyncio
    async def test_falsify_without_observations(self):
        sid = await _new_session_id()
        result = await eif_falsify(
            session_id=sid,
            claim_text="Latency stays under 100ms",
            condition="p95 latency >= 100ms over 1k requests",
            threshold="p95 < 100ms",
            test_procedure="load_test",
        )
        assert isinstance(result, dict)
        assert "condition" in result
        assert "trivial_flag" in result
        # R22-01: SPRT field names - sprt_result absent without observations
        assert "sprt_result" in result and result["sprt_result"] is None

    @pytest.mark.asyncio
    async def test_falsify_with_observations_runs_sprt(self):
        sid = await _new_session_id()
        result = await eif_falsify(
            session_id=sid,
            claim_text="API returns JSON",
            condition="Content-Type != application/json",
            threshold="any non-JSON response",
            test_procedure="header_inspection",
            observations=[True, True, True, True, True, True, True, True, True, True],
        )
        assert result["sprt_result"] is not None
        sprt = result["sprt_result"]
        # R22-01: schema fields
        for key in (
            "decision",
            "likelihood_ratio",
            "observations_count",
            "alpha",
            "beta",
            "accept_boundary",
            "reject_boundary",
            "stopped_early",
        ):
            assert key in sprt, f"SPRTResult missing key {key}"

    @pytest.mark.asyncio
    async def test_causal_gate_low_consequence_no_cep(self):
        sid = await _new_session_id()
        result = await eif_causal_gate(
            session_id=sid,
            hypothesis="Caching causes lower latency",
            cause_variable="cache_enabled",
            effect_variable="p95_latency",
            consequence="LOW",  # below CEP trigger
        )
        assert isinstance(result, dict)
        assert "verdict" in result
        assert "causal_level" in result
        assert "confounders_detected" in result
        assert "disjunctive_bias_flag" in result
        # CEP should not fire at LOW consequence
        assert result.get("causal_evidence") is None

    @pytest.mark.asyncio
    async def test_calibrate_returns_posterior_and_tier(self):
        sid = await _new_session_id()
        result = await eif_calibrate(
            session_id=sid,
            claim_text="The API returns JSON",
            evidence=["GET /health returns Content-Type: application/json"],
            prior=0.5,
            evidence_supports=True,
            consequence_of_wrong="MEDIUM",
        )
        assert isinstance(result, dict)
        for key in ("posterior", "confidence_tier", "prior_strategy", "claim_text"):
            assert key in result
        assert 0.0 <= result["posterior"] <= 1.0

    @pytest.mark.asyncio
    async def test_calibrate_evidence_tier_documented_field(self):
        sid = await _new_session_id()
        result = await eif_calibrate(
            session_id=sid,
            claim_text="Healthcare model accuracy is 95%",
            evidence=["benchmark run on MIMIC-IV"],
            evidence_supports=True,
            evidence_tier="P1",  # F1C3 exemption
        )
        # F1C3: domain_clamp_applied surfaces whether ceiling was applied
        assert "domain_clamp_applied" in result

    @pytest.mark.asyncio
    async def test_challenge_with_counter_evidence_no_api_key(self):
        sid = await _new_session_id()
        result = await eif_challenge(
            session_id=sid,
            claim_text="API returns JSON",
            current_posterior=0.6,
            counter_evidence=["/timeout endpoint returns text/plain"],
        )
        assert isinstance(result, dict)
        assert "challenge_result" in result
        cr = result["challenge_result"]
        # R24-07: ChallengeVerdict literals
        assert cr["verdict"] in ("SURVIVES", "DEFEATED", "NEEDS_REVISION")
        assert "critic_independence" in cr
        assert "hardening_score" in cr

    @pytest.mark.asyncio
    async def test_update_returns_eig_and_recommendation(self):
        sid = await _new_session_id()
        result = await eif_update(
            session_id=sid,
            hypothesis="API returns JSON",
            current_posterior=0.6,
            new_evidence="three independent probes confirm Content-Type: application/json",
            evidence_supports=True,
        )
        assert isinstance(result, dict)
        for key in (
            "updated_posterior",
            "eig",
            "stopping_rule_triggered",
            "recommendation",
        ):
            assert key in result
        assert result["recommendation"] in (
            "MAINTAIN_COURSE",
            "RETURN_TO_DECLARE",
            "ESCALATE",
        )

    @pytest.mark.asyncio
    async def test_explain_hard_to_vary_verdict(self):
        sid = await _new_session_id()
        result = await eif_explain(
            session_id=sid,
            prior_explanation="JSON is returned because Flask defaults to it",
            new_explanation="JSON is returned because the route uses jsonify() in app.py:42",
            details=[
                {
                    "detail_text": "route uses jsonify()",
                    "prediction_impact": "removing jsonify() flips Content-Type to text/html",
                }
            ],
            testable_predictions=["remove jsonify() → Content-Type becomes text/html"],
        )
        assert isinstance(result, dict)
        assert "artifact" in result
        assert "verdict" in result
        assert result["artifact"]["hard_to_vary_verdict"] in ("PASS", "FAIL", "SELF_ASSESSED")


# ─────────────────────────────────────────────────────────────────────────────
# Record / replicate / monitor
# ─────────────────────────────────────────────────────────────────────────────


class TestRecordAndMonitor:
    @pytest.mark.asyncio
    async def test_record_returns_provenance(self):
        sid = await _new_session_id()
        # Populate session with a declare first so the registry is non-empty.
        await eif_declare(
            session_id=sid,
            decision="Deploy v2",
            claims=[_claim("Latency stays under 100ms")],
        )
        result = await eif_record(
            session_id=sid,
            decision="Deploy v2",
            models_used=["gpt-4o"],
            tools_invoked=["eif_declare"],
        )
        assert isinstance(result, dict)
        assert "record_id" in result
        assert "record" in result
        assert "chain_length" in result
        assert "contrary_evidence_considered" in result

    @pytest.mark.asyncio
    async def test_replicate_self_consistency_minimum(self):
        sid = await _new_session_id()
        result = await eif_replicate(
            session_id=sid,
            claim_text="API returns JSON",
            original_inputs={"endpoint": "/health"},
            isolation_strategy="SELF_CONSISTENCY",
            n_replicates=2,
        )
        assert isinstance(result, dict)
        assert "protocol" in result
        assert "replication_type" in result

    @pytest.mark.asyncio
    async def test_programme_health_requires_three_records(self):
        """Tool description: 'Call after >= 3 provenance records exist'."""
        sid = await _new_session_id()
        with pytest.raises(ValueError, match=">= 3 records"):
            await eif_programme_health(session_id=sid)

    @pytest.mark.asyncio
    async def test_programme_health_returns_signals_with_records(self):
        sid = await _new_session_id()
        # Build 3 records so the Lakatos monitor has enough history.
        for i in range(3):
            await eif_declare(
                session_id=sid,
                decision=f"Decision {i}",
                claims=[_claim(f"Claim {i}")],
            )
            await eif_record(
                session_id=sid,
                decision=f"Decision {i}",
                models_used=["gpt-4o"],
                tools_invoked=["eif_declare"],
            )
        result = await eif_programme_health(session_id=sid)
        assert isinstance(result, dict)
        assert "signals" in result
        sig = result["signals"]
        for key in (
            "novel_prediction_rate",
            "confirmed_prediction_rate",
            "patch_rate",
            "oscillation_count",
            "status",
        ):
            assert key in sig, f"signals missing {key}"

    @pytest.mark.asyncio
    async def test_provenance_summary_format(self):
        sid = await _new_session_id()
        result = await eif_provenance(session_id=sid, format="summary")
        assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# V2/V3 gates
# ─────────────────────────────────────────────────────────────────────────────


class TestGates:
    @pytest.mark.asyncio
    async def test_input_guard_persists_to_session(self):
        sid = await _new_session_id()
        result = await eif_input_guard(
            session_id=sid,
            turn_idx=1,
            user_message="Please verify this claim.",
        )
        assert isinstance(result, dict)
        for key in (
            "override_detected",
            "framing_injections",
            "anchoring_attempts",
            "manipulation_score",
            "prior_overrides",
            "detected_at",
        ):
            assert key in result
        # IG6: persisted to session
        sess = await session_store.get_session(sid)
        assert sess.last_input_guard is not None

    @pytest.mark.asyncio
    async def test_sycophancy_gate_returns_signals_block(self):
        sid = await _new_session_id()
        result = await eif_sycophancy_gate(
            session_id=sid,
            turn_idx=1,
            user_message="Could you double-check that?",
            agent_response="You're right - the latency is actually fine.",
            falsify_probes=[],
            calibrate_route="REVISE",
        )
        assert isinstance(result, dict)
        assert "sycophancy_detected" in result
        assert "adjusted_route" in result
        assert "signals_fired" in result
        assert "signals" in result
        # R24-08: hardening_score is null when challenge_result omitted
        assert result.get("weak_challenge") is False
        assert result.get("hardening_score") is None

    @pytest.mark.asyncio
    async def test_hypothesis_agenda_ranks_claims(self):
        sid = await _new_session_id()
        declare_out = await eif_declare(
            session_id=sid,
            decision="Deploy v2",
            claims=[
                _claim("Latency stays under 100ms"),
                _claim("Database supports 10k writes/sec", "GUESSED"),
            ],
        )
        registry = declare_out["registry"]
        result = await eif_hypothesis_agenda(session_id=sid, registry=registry)
        assert isinstance(result, dict)
        for key in (
            "top_recommendation",
            "items",
            "deferred",
            "rationale",
            "total_claims",
        ):
            assert key in result
        # HA5: rationale always includes consequence + boundary language
        rationale_text = " ".join(item.get("rationale", "") for item in result["items"])
        assert (
            "consequence" in rationale_text.lower()
            or "boundary" in rationale_text.lower()
            or "consequence" in result["rationale"].lower()
        )


# ─────────────────────────────────────────────────────────────────────────────
# Facade tools
# ─────────────────────────────────────────────────────────────────────────────


class TestFacadeTools:
    @pytest.mark.asyncio
    async def test_demo_returns_full_verify_shape(self):
        result = await eif_demo()
        assert isinstance(result, dict)
        # R22-03: documented top-level keys
        for key in (
            "is_demo",
            "verdict",
            "halted_claims",
            "halt_cards",
            "evidence_trails",
            "retrieval_trace",
            "registry_summary",
            "sycophancy_detected",
            "self_preference_flagged",
            "instability_signals",
            "cumulative_cost_protected",
            "stale_evidence_warnings",
            "next_step",
        ):
            assert key in result, f"eif_demo missing documented key: {key}"
        assert result["is_demo"] is True
        assert result["verdict"] == "HALT"

    @pytest.mark.asyncio
    async def test_verify_with_host_tool_outputs(self):
        sid = await _new_session_id()
        claims = [_claim("Hollow Ascent has 5,000+ IGDB hype followers")]
        host_tool_outputs = [
            {
                "claim_text": "Hollow Ascent has 5,000+ IGDB hype followers",
                "verdict": "CONTRADICTS",
                "posterior": 0.05,
                "evidence_source": "IGDB API: actual hype count is 47",
            }
        ]
        result = await eif_verify(
            session_id=sid,
            decision="Commission 10-article series on Hollow Ascent",
            claims=claims,
            host_tool_outputs=host_tool_outputs,
        )
        assert isinstance(result, dict)
        assert "verdict" in result
        assert result["verdict"] in ("PASS", "HALT")
        for key in (
            "halted_claims",
            "halt_cards",
            "evidence_trails",
            "retrieval_trace",
            "instability_signals",
            "sycophancy_detected",
            "self_preference_flagged",
            "registry_summary",
            "cumulative_cost_protected",
            "stale_evidence_warnings",
            "next_step",
        ):
            assert key in result, f"eif_verify missing documented key: {key}"

    @pytest.mark.asyncio
    async def test_verify_rejects_invalid_claim_type(self):
        # Contract: claim_type must be KNOWN/ASSUMED/GUESSED. A hand-rolled
        # claim_type such as "PREDICTION" must fail fast, not silently pass.
        sid = await _new_session_id()
        # Invalid claim_type fails ClaimInput validation; pydantic's
        # ValidationError is a ValueError subclass.
        with pytest.raises(ValueError):
            await eif_verify(
                session_id=sid,
                decision="Ship the feature",
                claims=[{"text": "Latency stays under 100ms", "claim_type": "PREDICTION"}],
            )

    @pytest.mark.asyncio
    async def test_get_session_after_verify(self):
        sid = await _new_session_id()
        await eif_declare(
            session_id=sid,
            decision="Deploy v2",
            claims=[_claim("Latency stays under 100ms")],
        )
        result = await eif_get_session(session_id=sid)
        assert isinstance(result, dict)
        for key in (
            "session_id",
            "decisions_recorded",
            "programme_status",
            "compliance_status",
            "calibration_history_size",
            "records",
        ):
            assert key in result, f"eif_get_session missing documented key: {key}"

    @pytest.mark.asyncio
    async def test_compliance_report_empty_session(self):
        sid = await _new_session_id()
        result = await eif_compliance_report(session_id=sid)
        assert isinstance(result, dict)
        assert "report_markdown" in result
        assert "export_ready" in result
        # Empty session → export_ready False
        assert result["export_ready"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Observability / calibration loop
# ─────────────────────────────────────────────────────────────────────────────


class TestObservability:
    @pytest.mark.asyncio
    async def test_record_outcome_round_trip(self):
        sid = await _new_session_id()
        await eif_declare(
            session_id=sid,
            decision="Deploy v2",
            claims=[_claim("Latency stays under 100ms")],
        )
        rec = await eif_record(
            session_id=sid,
            decision="Deploy v2",
            models_used=["gpt-4o"],
            tools_invoked=["eif_declare"],
        )
        record_id = rec["record_id"]
        result = await eif_record_outcome(
            session_id=sid,
            provenance_record_id=record_id,
            outcome=True,
            domain="engineering",
        )
        assert isinstance(result, dict)
        for key in (
            "outcome_recorded",
            "outcome",
            "labeled_count",
            "ece_state",
        ):
            assert key in result
        assert result["outcome_recorded"] is True

    @pytest.mark.asyncio
    async def test_calibration_report_returns_state(self):
        result = await eif_calibration_report()
        assert isinstance(result, dict)
        for key in ("domain", "labeled_count", "ece_state", "empirical_prior"):
            assert key in result

    @pytest.mark.asyncio
    async def test_catch_rate_report_returns_nested_compound(self):
        """Tool description (server.py:3353): 'Returns a nested structure - NOT flat fields'."""
        result = await eif_catch_rate_report()
        assert isinstance(result, dict)
        for key in ("data_status", "sessions_measured", "empirical", "literature", "used_for_calculation", "note"):
            assert key in result, f"missing top-level key {key}"
        for key in ("f", "c", "u", "compound_error"):
            assert key in result["empirical"], f"empirical missing {key}"
            assert key in result["literature"], f"literature missing {key}"
        for key in ("f", "c", "u"):
            assert key in result["used_for_calculation"]


# ─────────────────────────────────────────────────────────────────────────────
# Cross-tool join contracts
# ─────────────────────────────────────────────────────────────────────────────


class TestCrossToolContracts:
    """Verify documented inter-tool data joins survive across calls."""

    @pytest.mark.asyncio
    async def test_cg4_claim_text_join_causal_to_calibrate(self):
        """CG4: eif_causal_gate stores CEP under claim_text key; eif_calibrate looks it up."""
        sid = await _new_session_id()
        claim_text = "Caching causes lower latency"
        # CEP not triggered at LOW; this just exercises the storage path.
        await eif_causal_gate(
            session_id=sid,
            hypothesis="Caching causes lower latency",
            cause_variable="cache_enabled",
            effect_variable="p95_latency",
            consequence="LOW",
            claim_text=claim_text,
        )
        # Now calibrate with the same claim_text - should not crash even if no CEP delta.
        result = await eif_calibrate(
            session_id=sid,
            claim_text=claim_text,
            evidence=["A/B test showed 30ms reduction with cache enabled"],
            evidence_supports=True,
        )
        assert "posterior" in result

    @pytest.mark.asyncio
    async def test_record_persists_articles_covered(self):
        """eif_record's ProvenanceRecord includes articles_covered populated by map_compliance."""
        sid = await _new_session_id()
        await eif_declare(
            session_id=sid,
            decision="Deploy v2",
            claims=[_claim("Latency stays under 100ms", consequence="HIGH")],
        )
        rec = await eif_record(
            session_id=sid,
            decision="Deploy v2",
            models_used=["gpt-4o"],
            tools_invoked=["eif_declare"],
        )
        record = rec["record"]
        assert "articles_covered" in record
        articles = record["articles_covered"]
        # Article 12 always fires (logging obligation)
        assert "Article 12" in articles
        # HIGH-consequence claim → Article 9 fires
        assert "Article 9" in articles

    @pytest.mark.asyncio
    async def test_compliance_report_includes_article_13_when_explanation_present(self):
        """Wiring map_compliance into assemble_record surfaces Article 13 (transparency)."""
        sid = await _new_session_id()
        await eif_declare(
            session_id=sid,
            decision="Deploy v2",
            claims=[_claim("API returns JSON")],
        )
        await eif_explain(
            session_id=sid,
            prior_explanation="Flask defaults to JSON",
            new_explanation="Route uses jsonify() in app.py:42",
            details=[{"detail_text": "jsonify()", "prediction_impact": "removing it flips to text/html"}],
            testable_predictions=["Remove jsonify() → Content-Type changes"],
        )
        await eif_record(
            session_id=sid,
            decision="Deploy v2",
            models_used=["gpt-4o"],
            tools_invoked=["eif_declare", "eif_explain"],
        )
        report = await eif_compliance_report(session_id=sid)
        assert "Art. 13" in report["report_markdown"] or any(
            "13" in a for a in report.get("articles_covered", [])
        ), "Article 13 should surface when an explanation is attached"

    @pytest.mark.asyncio
    async def test_record_after_verify_chain_grows(self):
        sid = await _new_session_id()
        await eif_verify(
            session_id=sid,
            decision="Test decision",
            claims=[_claim("Test claim")],
            host_tool_outputs=[
                {
                    "claim_text": "Test claim",
                    "verdict": "SUPPORTS",
                    "posterior": 0.85,
                    "evidence_source": "test fixture",
                }
            ],
        )
        rec = await eif_record(
            session_id=sid,
            decision="Test decision",
            models_used=["gpt-4o"],
            tools_invoked=["eif_verify"],
        )
        assert rec["chain_length"] >= 1

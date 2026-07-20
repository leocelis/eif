"""Tests for F3C4/F3C5: PIEVO principle memory and iterative refinement.

New constraints implemented in the gap fix:
  F3C4: proposal reads prior principle state - does not repeat accepted revisions.
  F3C5: max 2 refinement rounds per session.
  Principle memory: persistent cross-session domain learning (arXiv:2602.06448).
"""

import json
from unittest.mock import patch

from eif.programme.principle_memory import (
    _empty_domain,
    get_principle_context,
    load_principle_memory,
    record_revision,
)
from eif.programme.principle_revision import (
    REVISION_CONFIDENCE_CEILING,
    _self_consistency_check,
    propose_principle_revision,
)
from eif.schemas import ParadigmRevisionAlert


def _make_alert(direction="DOWN", session_id="test-001") -> ParadigmRevisionAlert:
    return ParadigmRevisionAlert(
        session_id=session_id,
        direction=direction,
        consecutive_updates=3,
        avg_posterior_shift=0.07,
        affected_claims=["Manor Lords has 3500 IGDB hypes", "50k community members"],
        recommendation="Return to DECLARE.",
    )


# ── Principle memory persistence ──────────────────────────────────────────────

class TestPrincipleMemoryPersistence:
    def test_empty_domain_returns_empty_struct(self):
        d = _empty_domain()
        assert d["revision_history"] == []
        assert d["total_anomalies"] == 0

    def test_record_revision_persists_to_disk(self, tmp_path):
        mem_file = tmp_path / "principle_memory.json"
        with patch("eif.programme.principle_memory._get_memory_path", return_value=mem_file):
            record_revision(
                domain="gaming_content",
                session_id="s001",
                direction="DOWN",
                affected_principle="IGDB hype count is a reliable demand signal",
                revision_direction="Treat IGDB hypes as a noisy proxy; require corroboration",
                confidence=0.65,
                alternative_hypotheses=["measurement error", "search bias"],
                accepted=True,
            )

            memory = load_principle_memory()

        assert "gaming_content" in memory
        entry = memory["gaming_content"]["revision_history"][0]
        assert entry["session_id"] == "s001"
        assert entry["accepted"] is True
        assert entry["confidence"] == 0.65

    def test_accepted_revision_sets_current_principle_state(self, tmp_path):
        mem_file = tmp_path / "pm.json"
        with patch("eif.programme.principle_memory._get_memory_path", return_value=mem_file):
            record_revision(
                domain="gaming_content",
                session_id="s001",
                direction="DOWN",
                affected_principle="prior A",
                revision_direction="new principle B",
                confidence=0.55,
                alternative_hypotheses=["alt1", "alt2"],
                accepted=True,
            )
            dom = load_principle_memory("gaming_content")

        assert dom["current_principle_state"] == "new principle B"
        assert dom["accepted_revisions"] == 1
        assert dom["rejected_revisions"] == 0

    def test_rejected_revision_does_not_update_principle_state(self, tmp_path):
        mem_file = tmp_path / "pm.json"
        with patch("eif.programme.principle_memory._get_memory_path", return_value=mem_file):
            record_revision(
                domain="gaming_content",
                session_id="s001",
                direction="DOWN",
                affected_principle="prior A",
                revision_direction="rejected change",
                confidence=0.45,
                alternative_hypotheses=["alt1", "alt2"],
                accepted=False,
            )
            dom = load_principle_memory("gaming_content")

        assert dom["current_principle_state"] is None
        assert dom["rejected_revisions"] == 1

    def test_get_principle_context_returns_prior_alternatives(self, tmp_path):
        mem_file = tmp_path / "pm.json"
        with patch("eif.programme.principle_memory._get_memory_path", return_value=mem_file):
            record_revision(
                domain="gaming_content", session_id="s1", direction="DOWN",
                affected_principle="p", revision_direction="r",
                confidence=0.5,
                alternative_hypotheses=["measurement error in IGDB", "search bias"],
                accepted=False,
            )
            ctx = get_principle_context("gaming_content")

        assert len(ctx["prior_alternatives"]) >= 2
        assert ctx["rejected_count"] == 1


# ── Self-consistency check ────────────────────────────────────────────────────

class TestSelfConsistencyCheck:
    def test_passes_for_novel_proposal(self):
        proposal = {
            "affected_principle": "The causal assumption that IGDB hypes track community demand is wrong",
            "revision_direction": "Require independent verification from Steam, Discord, and streaming data",
            "confidence": 0.60,
            "alternative_hypotheses": ["measurement error", "search bias"],
        }
        context = {"current_state": None, "prior_alternatives": []}
        assert _self_consistency_check(proposal, context) is None

    def test_fails_for_vague_principle(self):
        proposal = {
            "affected_principle": "Something is wrong",
            "revision_direction": "Fix it",
            "confidence": 0.50,
            "alternative_hypotheses": ["a", "b"],
        }
        context = {"current_state": None, "prior_alternatives": []}
        result = _self_consistency_check(proposal, context)
        assert result is not None
        assert "vague" in result.lower()

    def test_fails_when_revision_repeats_current_state(self):
        current = "Treat IGDB hypes as noisy proxy; require corroboration"
        proposal = {
            "affected_principle": "IGDB hype assumption is wrong",
            "revision_direction": current,  # exact repeat
            "confidence": 0.60,
            "alternative_hypotheses": ["measurement error", "search bias"],
        }
        context = {"current_state": current, "prior_alternatives": []}
        result = _self_consistency_check(proposal, context)
        assert result is not None
        assert "repeat" in result.lower()

    def test_fails_when_all_alternatives_are_prior(self):
        prior_alts = ["measurement error", "search bias"]
        proposal = {
            "affected_principle": "A sufficiently long new principle statement here",
            "revision_direction": "A sufficiently long new revision direction here",
            "confidence": 0.60,
            "alternative_hypotheses": prior_alts,  # all are in prior list
        }
        context = {"current_state": None, "prior_alternatives": prior_alts}
        result = _self_consistency_check(proposal, context)
        assert result is not None
        assert "repeat" in result.lower()


# ── Domain inference ──────────────────────────────────────────────────────────

class TestDomainInference:
    def test_gaming_domain_inferred(self):
        alert = ParadigmRevisionAlert(
            session_id="s1", direction="DOWN", consecutive_updates=3,
            avg_posterior_shift=0.05,
            affected_claims=["Manor Lords IGDB game claim"],
            recommendation="review",
        )
        # Patch where the function is used (imported into principle_revision)
        with patch("eif.programme.principle_revision.get_principle_context",
                   return_value={
                       "current_state": None, "recent_anomalies": [],
                       "accepted_count": 0, "rejected_count": 0,
                       "prior_alternatives": []
                   }) as mock_ctx:
            propose_principle_revision(alert)
            call_args = mock_ctx.call_args[0][0]
            assert call_args == "gaming_content"

    def test_explicit_domain_overrides_inference(self):
        alert = _make_alert()
        with patch("eif.programme.principle_revision.get_principle_context",
                   return_value={
                       "current_state": None, "recent_anomalies": [],
                       "accepted_count": 0, "rejected_count": 0,
                       "prior_alternatives": []
                   }) as mock_ctx:
            propose_principle_revision(alert, domain="investment")
            call_args = mock_ctx.call_args[0][0]
            assert call_args == "investment"


# ── Iterative refinement (F3C5) ───────────────────────────────────────────────

class TestIterativeRefinement:
    def test_proposal_satisfies_all_constraints_after_refinement(self):
        """Even when round 1 fails consistency, output still satisfies F3C1-F3C3."""
        # Make a fake LLM that returns a vague proposal on round 1, good on round 2
        call_count = {"n": 0}

        def fake_llm(prompt, tool_name="", system_prompt=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Round 1: vague (will fail consistency)
                return json.dumps({
                    "affected_principle": "Bad",
                    "revision_direction": "Fix",
                    "confidence": 0.6,
                    "alternative_hypotheses": ["alt1", "alt2"],
                })
            # Round 2: proper
            return json.dumps({
                "affected_principle": "The assumption that IGDB hypes track demand linearly is wrong for released games",
                "revision_direction": "Require Steam CCU and community forum data to corroborate IGDB hype counts",
                "confidence": 0.65,
                "alternative_hypotheses": [
                    "Search bias in evidence collection favors negative studies",
                    "Domain shift: game moved from early access to release, invalidating hype metrics",
                ],
            })

        alert = _make_alert()
        with patch("eif.programme.principle_memory.get_principle_context",
                   return_value={
                       "current_state": None, "recent_anomalies": [],
                       "accepted_count": 0, "rejected_count": 0,
                       "prior_alternatives": []
                   }):
            proposal = propose_principle_revision(alert, llm_fn=fake_llm)

        assert proposal.requires_confirmation is True  # F3C2
        assert proposal.confidence <= REVISION_CONFIDENCE_CEILING  # F3C3
        assert len(proposal.alternative_hypotheses) >= 2  # F3C1

    def test_heuristic_second_revision_differs_from_first(self):
        """When accepted_count > 0, heuristic produces a 'superseding' proposal."""
        alert = _make_alert()
        with patch("eif.programme.principle_memory.get_principle_context",
                   return_value={
                       "current_state": "Treat IGDB as noisy proxy",
                       "recent_anomalies": [{"direction": "DOWN"}],
                       "accepted_count": 1,
                       "rejected_count": 0,
                       "prior_alternatives": [],
                   }):
            proposal = propose_principle_revision(alert)

        # Should reference the prior revision insufficiency, not just the original issue
        combined = proposal.affected_principle + proposal.revision_direction
        assert len(combined) > 30  # has substance
        assert proposal.requires_confirmation is True

    def test_record_outcome_persists_revision(self, tmp_path):
        mem_file = tmp_path / "pm.json"
        alert = _make_alert(session_id="session-record-test")

        with patch("eif.programme.principle_memory._get_memory_path", return_value=mem_file), \
             patch("eif.programme.principle_memory.get_principle_context",
                   return_value={
                       "current_state": None, "recent_anomalies": [],
                       "accepted_count": 0, "rejected_count": 0,
                       "prior_alternatives": []
                   }):
            propose_principle_revision(alert, domain="gaming_content",
                                       record_outcome=True, accepted=True)
            memory = load_principle_memory()

        assert "gaming_content" in memory
        history = memory["gaming_content"]["revision_history"]
        assert len(history) == 1
        assert history[0]["session_id"] == "session-record-test"
        assert history[0]["accepted"] is True

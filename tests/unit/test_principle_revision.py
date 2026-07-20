"""Tests for F3: PIEVO principle-level revision (V2).

Covers F3C1 (≥ 2 alternative_hypotheses), F3C2 (requires_confirmation always True),
F3C3 (confidence ≤ 0.80), and heuristic proposal generation.
"""

from eif.programme.principle_revision import (
    REVISION_CONFIDENCE_CEILING,
    propose_principle_revision,
)
from eif.schemas import ParadigmRevisionAlert


def _make_alert(direction="DOWN", n=3, avg_shift=0.05) -> ParadigmRevisionAlert:
    return ParadigmRevisionAlert(
        session_id="test-session",
        direction=direction,
        consecutive_updates=n,
        avg_posterior_shift=avg_shift,
        affected_claims=["claim A", "claim B"],
        recommendation="Consider returning to DECLARE.",
    )


# ── F3C1: ≥ 2 alternative hypotheses ─────────────────────────────────────────

class TestAlternativeHypotheses:
    def test_at_least_two_alternatives_down_alert(self):
        proposal = propose_principle_revision(_make_alert("DOWN"))
        assert len(proposal.alternative_hypotheses) >= 2, "F3C1: need ≥ 2 alternatives"

    def test_at_least_two_alternatives_up_alert(self):
        proposal = propose_principle_revision(_make_alert("UP"))
        assert len(proposal.alternative_hypotheses) >= 2

    def test_alternatives_are_strings(self):
        proposal = propose_principle_revision(_make_alert())
        for alt in proposal.alternative_hypotheses:
            assert isinstance(alt, str) and len(alt) > 10


# ── F3C2: requires_confirmation always True ───────────────────────────────────

class TestRequiresConfirmation:
    def test_always_true_for_down_alert(self):
        proposal = propose_principle_revision(_make_alert("DOWN"))
        assert proposal.requires_confirmation is True

    def test_always_true_for_up_alert(self):
        proposal = propose_principle_revision(_make_alert("UP"))
        assert proposal.requires_confirmation is True

    def test_always_true_regardless_of_llm_fn(self):
        def fake_llm(prompt, tool_name="", system_prompt=None):
            return '{"affected_principle": "X", "revision_direction": "Y", "confidence": 0.9, "alternative_hypotheses": ["a", "b"]}'

        proposal = propose_principle_revision(_make_alert(), llm_fn=fake_llm)
        assert proposal.requires_confirmation is True


# ── F3C3: confidence ≤ 0.80 ───────────────────────────────────────────────────

class TestConfidenceCeiling:
    def test_confidence_at_or_below_ceiling(self):
        proposal = propose_principle_revision(_make_alert())
        assert proposal.confidence <= REVISION_CONFIDENCE_CEILING, "F3C3: ceiling 0.80"

    def test_llm_overconfidence_clamped(self):
        """Even if LLM returns confidence=0.99, it must be clamped to 0.80."""
        def fake_llm(prompt, tool_name="", system_prompt=None):
            return '{"affected_principle": "X", "revision_direction": "Y", "confidence": 0.99, "alternative_hypotheses": ["a", "b", "c"]}'

        proposal = propose_principle_revision(_make_alert(), llm_fn=fake_llm)
        assert proposal.confidence <= 0.80

    def test_confidence_positive(self):
        proposal = propose_principle_revision(_make_alert())
        assert proposal.confidence > 0.0


# ── Supporting evidence from claims ───────────────────────────────────────────

class TestSupportingEvidence:
    def test_supporting_evidence_included_from_claims(self):
        class FakeClaim:
            text = "claim A"

        proposal = propose_principle_revision(_make_alert(), claims=[FakeClaim()])
        assert len(proposal.supporting_evidence) >= 1
        assert "claim A" in proposal.supporting_evidence[0]

    def test_direction_set_from_alert(self):
        proposal = propose_principle_revision(_make_alert("DOWN"))
        assert proposal.triggered_by_alert_direction == "DOWN"

    def test_session_id_propagated(self):
        proposal = propose_principle_revision(_make_alert())
        assert proposal.session_id == "test-session"


# ── LLM path with bad JSON → heuristic fallback ───────────────────────────────

class TestLLMFallback:
    def test_bad_llm_response_falls_back_to_heuristic(self):
        def bad_llm(prompt, tool_name="", system_prompt=None):
            return "not json at all"

        proposal = propose_principle_revision(_make_alert(), llm_fn=bad_llm)
        # Should still produce a valid proposal via heuristic
        assert len(proposal.alternative_hypotheses) >= 2
        assert proposal.requires_confirmation is True

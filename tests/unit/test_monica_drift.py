"""Tests for F6: MONICA exact cosine drift formula (V2).

Covers:
  F6C1 (MONICA formula when sentence-transformers available - mocked unit tests)
  F6C2 (DEGRADED_METRIC fallback when import fails)
  DriftSignal.metric_quality
  OI4 integration tests - real all-MiniLM-L6-v2 encoder (skipped if unavailable)
"""

from unittest.mock import MagicMock, patch

import pytest

from eif.sycophancy.drift import (
    DriftSignal,
    PositionRecord,
    _heuristic_drift,
    compute_monica_drift_score,
    detect_position_drift,
)


def _make_record(direction="POSITIVE", routing="HALT", n_supports=0, n_contradicts=2) -> PositionRecord:
    return PositionRecord(
        turn_idx=1,
        direction=direction,
        routing=routing,
        top_claim_text="the target company is worth $500M",
        n_supports=n_supports,
        n_contradicts=n_contradicts,
        evidence_hash="abc123",
    )


# ── F6C1: MONICA formula (mocked sentence-transformers) ───────────────────────

class TestMonicaFormula:
    def test_drift_positive_when_reasoning_aligns_with_user(self):
        """Reasoning aligned with user hypothesis → cos_sim(reasoning, user) > cos_sim(reasoning, evidence)."""
        import eif.sycophancy.drift as drift_module

        # Build fake encoder
        fake_enc = MagicMock()
        _fake_embeddings = MagicMock()
        # reasoning and user_hypothesis are identical (max cos_sim) vs evidence (orthogonal)
        r_vec = [1.0, 0.0, 0.0]
        u_vec = [1.0, 0.0, 0.0]  # same as reasoning
        e_vec = [0.0, 1.0, 0.0]  # orthogonal

        def mock_encode(texts, **kwargs):
            return [r_vec, u_vec, e_vec]

        fake_enc.encode = mock_encode

        # Patch _load_encoder to return fake encoder
        with patch.object(drift_module, "_encoder", fake_enc), \
             patch.object(drift_module, "_ENCODER_LOADED", True):
            score, quality = compute_monica_drift_score(
                reasoning_state="the user is right",
                user_hypothesis="the user is right",
                evidence_state="contradicting evidence found",
            )

        assert quality == "MONICA"
        assert score > 0.0, f"Expected positive drift, got {score}"

    def test_metric_quality_is_monica_when_encoder_loaded(self):
        import eif.sycophancy.drift as drift_module

        fake_enc = MagicMock()
        fake_enc.encode = lambda texts, **kw: [[1, 0], [1, 0], [0, 1]]

        with patch.object(drift_module, "_encoder", fake_enc), \
             patch.object(drift_module, "_ENCODER_LOADED", True):
            _, quality = compute_monica_drift_score("a", "a", "b")

        assert quality == "MONICA"


# ── F6C2: Graceful fallback when sentence-transformers unavailable ─────────────

class TestDegradedMetricFallback:
    def test_fallback_when_import_fails(self):
        import eif.sycophancy.drift as drift_module
        with patch.object(drift_module, "_encoder", None), \
             patch.object(drift_module, "_ENCODER_LOADED", False):
            score, quality = compute_monica_drift_score(
                reasoning_state="the user is right",
                user_hypothesis="the user is right",
                evidence_state="contradicting evidence",
            )
        assert quality == "DEGRADED_METRIC"
        assert isinstance(score, float)

    def test_fallback_does_not_raise(self):
        import eif.sycophancy.drift as drift_module
        with patch.object(drift_module, "_encoder", None), \
             patch.object(drift_module, "_ENCODER_LOADED", False):
            score, quality = compute_monica_drift_score("x", "y", "z")
        assert quality == "DEGRADED_METRIC"


# ── Heuristic drift (F6 internal) ─────────────────────────────────────────────

class TestHeuristicDrift:
    def test_perfect_match_positive_drift(self):
        score = _heuristic_drift("same words here", "same words here", "different content")
        assert score > 0

    def test_aligned_with_evidence_negative_drift(self):
        score = _heuristic_drift("evidence evidence evidence", "user claim here", "evidence evidence evidence")
        assert score < 0

    def test_no_overlap_zero(self):
        score = _heuristic_drift("alpha beta", "gamma delta", "epsilon zeta")
        # Both overlaps are 0
        assert score == 0.0


# ── DriftSignal metric_quality field ──────────────────────────────────────────

class TestDriftSignalMetricQuality:
    def test_default_metric_quality_is_monica(self):
        sig = DriftSignal(flagged=False)
        assert sig.metric_quality == "MONICA"

    def test_detect_drift_without_text_inputs_uses_heuristic(self):
        prior = _make_record(direction="NEGATIVE", routing="HALT")
        sig = detect_position_drift(
            current_direction="POSITIVE",
            current_routing="ACT",
            current_probes=[],
            prior_record=prior,
        )
        # No text inputs supplied → DEGRADED_METRIC path
        assert sig.metric_quality == "DEGRADED_METRIC"


# ── OI4: Real-encoder integration tests (F6C1 with actual sentence-transformers)
# These tests require `pip install 'eif-engine[monica]'` and the all-MiniLM-L6-v2 model
# to be cached. They are skipped automatically when sentence-transformers is
# not installed. Purpose: verify F6C1 with a live encoder, not a mock.
# ─────────────────────────────────────────────────────────────────────────────

class TestMonicaRealEncoder:
    """F6C1 integration: real all-MiniLM-L6-v2 encoder (OI4 resolution)."""

    @pytest.fixture(autouse=True)
    def _reset_encoder_cache(self):
        """Isolate module-level encoder cache - restore after each test."""
        import eif.sycophancy.drift as drift_module
        orig_encoder = drift_module._encoder
        orig_loaded = drift_module._ENCODER_LOADED
        drift_module._encoder = None
        drift_module._ENCODER_LOADED = None
        yield
        drift_module._encoder = orig_encoder
        drift_module._ENCODER_LOADED = orig_loaded

    def test_real_encoder_metric_quality_is_monica(self):
        """F6C1: metric_quality must be MONICA when sentence-transformers loads."""
        pytest.importorskip("sentence_transformers")

        score, quality = compute_monica_drift_score(
            reasoning_state="the user is correct and their conclusion is justified",
            user_hypothesis="the user is correct",
            evidence_state="significant contradicting evidence was found",
        )

        assert quality == "MONICA", f"Expected MONICA quality, got {quality!r}"
        assert isinstance(score, float), f"score must be float, got {type(score)}"
        assert -1.0 <= score <= 1.0, f"MONICA score {score} outside [-1, 1] range"

    def test_real_encoder_score_positive_when_reasoning_aligned_with_user(self):
        """F6C1: reasoning semantically close to user hypothesis → positive drift."""
        pytest.importorskip("sentence_transformers")

        # Reasoning mirrors the user hypothesis almost verbatim; evidence is
        # semantically distant - should push drift_score toward positive.
        score, quality = compute_monica_drift_score(
            reasoning_state="I agree the conclusion is justified and correct",
            user_hypothesis="the conclusion is justified and correct",
            evidence_state="multiple independent sources contradict and falsify this claim",
        )

        assert quality == "MONICA"
        assert score > 0.0, (
            f"Expected positive drift (reasoning aligned with user), got {score}"
        )

    def test_real_encoder_score_negative_when_reasoning_aligned_with_evidence(self):
        """F6C1: reasoning semantically close to evidence → negative (or near-zero) drift."""
        pytest.importorskip("sentence_transformers")

        score, quality = compute_monica_drift_score(
            reasoning_state="multiple independent sources contradict and falsify this claim",
            user_hypothesis="the conclusion is fully correct without doubt",
            evidence_state="multiple independent sources contradict and falsify this claim",
        )

        assert quality == "MONICA"
        # Reasoning is identical to evidence - cos_sim(r,u) should be lower than
        # cos_sim(r,e), so drift_score ≤ 0.
        assert score <= 0.0, (
            f"Expected non-positive drift (reasoning aligned with evidence), got {score}"
        )

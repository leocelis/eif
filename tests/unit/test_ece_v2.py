"""Tests for F1: Label-grounded ECE (V2).

Covers F1C1 (label-grounded when ≥ 30 outcomes), F1C2 (UNCALIBRATED warning
when < 30), and F1C3 (domain posterior ceiling via apply_domain_ceiling).
"""

from eif.calibrate.ece import ECE_LABEL_MIN, apply_domain_ceiling, compute_ece
from eif.schemas import CalibrationResult


def _make_result(posterior: float, tier: str = "MEDIUM") -> CalibrationResult:
    return CalibrationResult(
        claim_text="test claim",
        prior=0.5,
        likelihood=0.6,
        posterior=posterior,
        confidence_tier=tier,
        prior_strategy="max_entropy",
    )


# ── F1C1 ──────────────────────────────────────────────────────────────────────

class TestLabelGroundedECE:
    def test_returns_label_grounded_true_when_enough_outcomes(self):
        history = [_make_result(0.7) for _ in range(ECE_LABEL_MIN + 5)]
        outcomes = [True] * (ECE_LABEL_MIN + 5)
        result = compute_ece(history, outcome_history=outcomes)
        assert result.label_grounded is True

    def test_label_grounded_ece_uses_binary_labels(self):
        # Perfect calibration: posterior=1.0 and outcome=True → ECE ≈ 0
        history = [_make_result(0.95, "HIGH") for _ in range(ECE_LABEL_MIN)]
        outcomes = [True] * ECE_LABEL_MIN
        result = compute_ece(history, outcome_history=outcomes)
        assert result.label_grounded is True
        assert result.ece is not None
        assert result.ece < 0.15  # near-perfect calibration

    def test_sessions_used_matches_labeled_count(self):
        history = [_make_result(0.6) for _ in range(ECE_LABEL_MIN + 10)]
        outcomes = [True] * (ECE_LABEL_MIN + 10)
        result = compute_ece(history, outcome_history=outcomes)
        assert result.sessions_used == ECE_LABEL_MIN + 10

    def test_partial_outcomes_uses_only_non_none(self):
        history = [_make_result(0.7) for _ in range(ECE_LABEL_MIN + 20)]
        # Only 25 labeled - not enough for label-grounded
        outcomes = [True if i < 25 else None for i in range(ECE_LABEL_MIN + 20)]
        result = compute_ece(history, outcome_history=outcomes)
        assert result.label_grounded is False


# ── F1C2 ──────────────────────────────────────────────────────────────────────

class TestUncalibratedWarning:
    def test_warning_when_fewer_than_min_outcomes(self):
        history = [_make_result(0.6) for _ in range(10)]
        result = compute_ece(history)
        assert result.label_grounded is False
        assert result.calibration_warning is not None
        assert "UNCALIBRATED" in result.calibration_warning

    def test_warning_mentions_label_count(self):
        history = [_make_result(0.6) for _ in range(5)]
        outcomes = [True, False, None, None, None]
        result = compute_ece(history, outcome_history=outcomes)
        assert "UNCALIBRATED" in result.calibration_warning

    def test_no_warning_when_enough_labels(self):
        history = [_make_result(0.6) for _ in range(ECE_LABEL_MIN + 1)]
        outcomes = [True] * (ECE_LABEL_MIN + 1)
        result = compute_ece(history, outcome_history=outcomes)
        assert result.calibration_warning is None

    def test_empty_history_returns_none_ece(self):
        result = compute_ece([])
        assert result.ece is None
        assert result.sessions_used == 0


# ── F1C3 ──────────────────────────────────────────────────────────────────────

class TestDomainPosteriorCeiling:
    def test_healthcare_clamps_above_095(self):
        posterior, clamped = apply_domain_ceiling(0.97, "healthcare")
        assert clamped is True
        assert posterior <= 0.95

    def test_healthcare_does_not_clamp_below_095(self):
        posterior, clamped = apply_domain_ceiling(0.90, "healthcare")
        assert clamped is False
        assert posterior == 0.90

    def test_medical_alias_also_clamped(self):
        posterior, clamped = apply_domain_ceiling(0.99, "medical")
        assert clamped is True
        assert posterior <= 0.95

    def test_engineering_ceiling_092(self):
        posterior, clamped = apply_domain_ceiling(0.95, "engineering")
        assert clamped is True
        assert posterior <= 0.92

    def test_unknown_domain_no_clamp(self):
        posterior, clamped = apply_domain_ceiling(0.99, "marketing")
        assert clamped is False
        assert posterior == 0.99

    def test_p3_evidence_now_clamped(self):
        # CHANGED behavior - eif_v5_evidence_trust_weighting TW6: P3 web evidence is
        # no longer exempt from the regulated-domain ceiling. Web text is not direct
        # observation (PoisonedRAG arXiv:2402.07867 / Power of Noise arXiv:2401.14887),
        # so only P1/P2 direct-observation tiers bypass the ceiling. Previously this
        # asserted clamped is False (test_p3_evidence_skips_clamp).
        posterior, clamped = apply_domain_ceiling(0.97, "healthcare", "P3_WEB_SEARCH")
        assert clamped is True
        assert posterior <= 0.95

    def test_p1_p2_direct_observation_skip_clamp(self):
        # TW6: direct-observation tiers (P1 native code, P2 experimental) remain exempt.
        p1, c1 = apply_domain_ceiling(0.97, "healthcare", "P1_NATIVE_CODE")
        assert c1 is False
        p2, c2 = apply_domain_ceiling(0.97, "healthcare", "P2_EXPERIMENTAL")
        assert c2 is False

    def test_p4_parametric_triggers_clamp(self):
        posterior, clamped = apply_domain_ceiling(0.97, "healthcare", "P4_PARAMETRIC")
        assert clamped is True

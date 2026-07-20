"""Tests for independent convergent replication - Extension B (F13)."""

from __future__ import annotations

import pytest

from eif.replicate.independent import _routing_from_posterior, run_independent_replication
from eif.schemas import (
    THRESHOLD_ACT,
    THRESHOLD_HALT,
    AssumptionRegistry,
    CalibrationResult,
    Claim,
    IndependentReplicationResult,
    ProvenanceRecord,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_registry(session_id: str = "test-session") -> AssumptionRegistry:
    return AssumptionRegistry(
        session_id=session_id,
        decision="Test decision",
        known=[],
        assumed=[Claim(
            text="Test claim",
            claim_type="ASSUMED",
            consequence_of_wrong="HIGH",
        )],
        guessed=[],
    )


def _make_record(
    calibrations: list[dict],
    session_id: str = "test-session",
) -> ProvenanceRecord:
    registry = _make_registry(session_id)
    cal_objects = [
        CalibrationResult(
            claim_text=c.get("claim_text", "Test claim"),
            prior=c.get("prior", 0.5),
            likelihood=c.get("likelihood", 0.5),
            posterior=c.get("posterior", 0.5),
            confidence_tier="MEDIUM",
            prior_strategy="max_entropy",
        )
        for c in calibrations
    ]
    return ProvenanceRecord(
        session_id=session_id,
        decision="Test decision",
        registry=registry,
        calibration=cal_objects,
    )


# ─────────────────────────────────────────────────────────────────────────────
# _routing_from_posterior
# ─────────────────────────────────────────────────────────────────────────────

class TestRoutingHelper:

    def test_act_at_threshold(self):
        assert _routing_from_posterior(THRESHOLD_ACT) == "ACT"

    def test_act_above_threshold(self):
        assert _routing_from_posterior(0.90) == "ACT"

    def test_revise_between_thresholds(self):
        assert _routing_from_posterior(0.50) == "REVISE"

    def test_halt_at_threshold(self):
        # THRESHOLD_HALT is the lower bound of REVISE (>= THRESHOLD_HALT → REVISE)
        # so exactly at threshold → REVISE; strictly below → HALT
        assert _routing_from_posterior(THRESHOLD_HALT) == "REVISE"

    def test_halt_strictly_below_threshold(self):
        assert _routing_from_posterior(THRESHOLD_HALT - 0.001) == "HALT"

    def test_halt_below_threshold(self):
        assert _routing_from_posterior(0.10) == "HALT"


# ─────────────────────────────────────────────────────────────────────────────
# run_independent_replication
# ─────────────────────────────────────────────────────────────────────────────

class TestIndependentReplicationBasics:

    def test_returns_correct_type(self):
        """F13C1: must return IndependentReplicationResult."""
        record = _make_record([{"posterior": 0.15, "likelihood": 0.2, "prior": 0.7}])
        result = run_independent_replication(record)
        assert isinstance(result, IndependentReplicationResult)
        assert result.agreement_type in ("CONVERGENT", "DIVERGENT")

    def test_empty_calibration_vacuously_convergent(self):
        """F13C1: empty calibration → CONVERGENT (vacuously)."""
        record = _make_record([])
        result = run_independent_replication(record)
        assert result.agreement_type == "CONVERGENT"
        assert result.claims_compared == 0
        assert result.human_review_required is False

    def test_deterministic_on_same_record(self):
        """F13C3: calling twice on the same record must yield identical results."""
        record = _make_record([
            {"posterior": 0.10, "likelihood": 0.50, "prior": 0.70},
        ])
        result1 = run_independent_replication(record)
        result2 = run_independent_replication(record)
        assert result1.agreement_type == result2.agreement_type
        assert result1.original_routing == result2.original_routing
        assert result1.independent_routing == result2.independent_routing
        assert result1.diverged == result2.diverged

    def test_record_unchanged_after_replication(self):
        """F13C3: record must not be mutated by replication."""
        record = _make_record([{"posterior": 0.10, "likelihood": 0.50, "prior": 0.70}])
        original_cal = list(record.calibration)
        run_independent_replication(record)
        assert record.calibration == original_cal


class TestConvergentCases:

    def test_convergent_both_act(self):
        """Both original and flat-prior posteriors above THRESHOLD_ACT → CONVERGENT."""
        record = _make_record([
            {"posterior": 0.80, "likelihood": 0.75, "prior": 0.85},
        ])
        result = run_independent_replication(record)
        # flat posterior = likelihood = 0.75 → ACT; original = 0.80 → ACT
        assert result.agreement_type == "CONVERGENT"
        assert result.diverged is False

    def test_convergent_both_halt(self):
        """Both route to HALT regardless of prior → CONVERGENT."""
        record = _make_record([
            {"posterior": 0.10, "likelihood": 0.05, "prior": 0.5},
        ])
        result = run_independent_replication(record)
        # flat posterior = likelihood = 0.05 → HALT; original = 0.10 → HALT
        assert result.agreement_type == "CONVERGENT"


class TestDivergentCases:

    def test_divergent_halt_original_revise_independent(self):
        """F13C2: HALT original + REVISE independent → DIVERGENT + human_review."""
        # posterior=0.10 (HALT from high prior), likelihood=0.50 → flat=0.50 (REVISE)
        record = _make_record([
            {"posterior": 0.10, "likelihood": 0.50, "prior": 0.70},
        ])
        result = run_independent_replication(record)
        assert result.original_routing == "HALT"
        assert result.independent_routing == "REVISE"
        assert result.agreement_type == "DIVERGENT"
        assert result.human_review_required is True
        assert result.diverged is True

    def test_divergent_act_original_halt_independent(self):
        """High empirical prior pushes to ACT; flat prior would HALT."""
        # posterior=0.75 (high prior boosts it to ACT), likelihood=0.10 → flat=0.10 (HALT)
        record = _make_record([
            {"posterior": 0.75, "likelihood": 0.10, "prior": 0.95},
        ])
        result = run_independent_replication(record)
        assert result.original_routing == "ACT"
        assert result.independent_routing == "HALT"
        assert result.agreement_type == "DIVERGENT"
        assert result.human_review_required is True

    def test_prior_sensitivity_reflects_delta(self):
        """prior_sensitivity must be |original_min - independent_min|."""
        record = _make_record([
            {"posterior": 0.10, "likelihood": 0.50, "prior": 0.70},
        ])
        result = run_independent_replication(record)
        expected = abs(0.10 - 0.50)
        assert result.prior_sensitivity == pytest.approx(expected, abs=1e-6)

    def test_multiple_claims_min_posterior_used(self):
        """Routing is determined by the minimum posterior across all claims."""
        record = _make_record([
            {"posterior": 0.80, "likelihood": 0.75, "prior": 0.90},  # ACT
            {"posterior": 0.10, "likelihood": 0.50, "prior": 0.70},  # HALT
        ])
        result = run_independent_replication(record)
        # Min original posterior = 0.10 → HALT
        assert result.original_routing == "HALT"
        # Min flat posterior = min(0.75, 0.50) = 0.50 → REVISE
        assert result.independent_routing == "REVISE"
        assert result.agreement_type == "DIVERGENT"
        assert result.claims_compared == 2

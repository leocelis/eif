"""Tests for UPDATE phase (C6 - EIG stopping rule)."""

from __future__ import annotations

import pytest

from eif.schemas import EIG_THRESHOLD, SPRTResult
from eif.update.eig import compute_eig
from eif.update.posterior import sequential_update
from eif.update.stopping import evaluate_stopping


class TestEIG:
    """C6: EIG = KL(posterior ∥ prior). EIG < 0.01 → stopping triggered."""

    def test_equal_prior_posterior_zero_eig(self):
        eig = compute_eig(prior=0.5, posterior=0.5)
        assert eig == 0.0

    def test_very_small_update_below_threshold(self):
        eig = compute_eig(prior=0.5, posterior=0.501)
        assert eig < EIG_THRESHOLD

    def test_large_update_above_threshold(self):
        eig = compute_eig(prior=0.3, posterior=0.9)
        assert eig > EIG_THRESHOLD

    def test_eig_non_negative(self):
        for p, q in [(0.5, 0.7), (0.9, 0.1), (0.1, 0.9)]:
            assert compute_eig(prior=p, posterior=q) >= 0.0

    def test_eig_edge_cases_handled(self):
        # Extreme values should not raise
        compute_eig(prior=0.0, posterior=1.0)
        compute_eig(prior=1.0, posterior=0.0)


class TestStoppingRule:
    """C6: evaluate_stopping returns (True, EIG_BELOW_THRESHOLD) when EIG < threshold."""

    def test_low_eig_triggers_stop(self):
        triggered, reason = evaluate_stopping(eig=0.001)
        assert triggered is True
        assert reason == "EIG_BELOW_THRESHOLD"

    def test_eig_at_threshold_does_not_trigger(self):
        triggered, _ = evaluate_stopping(eig=EIG_THRESHOLD)
        assert triggered is False

    def test_sprt_boundary_triggers_stop(self):
        sprt = SPRTResult(
            decision="ACCEPT",
            likelihood_ratio=0.1,
            observations_count=5,
            alpha=0.05,
            beta=0.10,
            accept_boundary=0.105,
            reject_boundary=18.0,
            stopped_early=True,
        )
        triggered, reason = evaluate_stopping(eig=0.05, sprt_result=sprt)
        assert triggered is True
        assert reason == "SPRT_BOUNDARY"

    def test_sprt_continue_does_not_trigger(self):
        sprt = SPRTResult(
            decision="CONTINUE",
            likelihood_ratio=1.0,
            observations_count=5,
            alpha=0.05,
            beta=0.10,
            accept_boundary=0.105,
            reject_boundary=18.0,
        )
        triggered, reason = evaluate_stopping(eig=0.05, sprt_result=sprt)
        assert triggered is False

    def test_cost_exceeds_value_triggers_stop(self):
        triggered, reason = evaluate_stopping(
            eig=0.05,
            decision_value=10.0,
            cost_estimate=20.0,
        )
        assert triggered is True
        assert reason == "COST_EXCEEDS_VALUE"


class TestSequentialUpdate:
    def test_supporting_evidence_increases_posterior(self):
        new_posterior, _ = sequential_update(prior_posterior=0.5, evidence_supports=True)
        assert new_posterior > 0.5

    def test_contrary_evidence_decreases_posterior(self):
        new_posterior, _ = sequential_update(prior_posterior=0.5, evidence_supports=False)
        assert new_posterior < 0.5

    def test_invalid_prior_raises(self):
        with pytest.raises(ValueError):
            sequential_update(prior_posterior=1.5, evidence_supports=True)

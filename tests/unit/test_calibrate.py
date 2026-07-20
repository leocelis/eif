"""Tests for CALIBRATE phase (C4, C5 - Bayesian posterior, prior strategy)."""

from __future__ import annotations

from eif.calibrate.bayesian import compute_posterior
from eif.calibrate.ece import compute_ece
from eif.calibrate.prior_strategy import empirical_bayes_prior, select_prior_strategy
from eif.schemas import PRIOR_EMPIRICAL_MIN, CalibrationResult


class TestBayesianPosterior:
    """C4: Posterior must be in (0, 1) and directionally correct."""

    def test_posterior_in_unit_interval(self):
        posterior, _ = compute_posterior(prior=0.5, evidence_supports=True)
        assert 0.0 < posterior < 1.0

    def test_supporting_evidence_increases_posterior(self):
        posterior, _ = compute_posterior(prior=0.5, evidence_supports=True)
        assert posterior > 0.5

    def test_contrary_evidence_decreases_posterior(self):
        posterior, _ = compute_posterior(prior=0.5, evidence_supports=False)
        assert posterior < 0.5

    def test_custom_likelihood_used(self):
        posterior_high, _ = compute_posterior(prior=0.5, evidence_supports=True, likelihood_estimate=0.9)
        posterior_low, _ = compute_posterior(prior=0.5, evidence_supports=True, likelihood_estimate=0.6)
        assert posterior_high > posterior_low

    def test_extreme_prior_stays_bounded(self):
        posterior, _ = compute_posterior(prior=0.001, evidence_supports=True)
        assert 0.0 <= posterior <= 1.0

    def test_fallibilism_epsilon_guard_never_zero(self):
        """Deutsch fallibilism: posterior must never reach exact 0.0 or 1.0."""
        posterior_low, _ = compute_posterior(prior=0.0, evidence_supports=False)
        assert posterior_low > 0.0, "Fallibilism guard: posterior must be > 0"

    def test_fallibilism_epsilon_guard_never_one(self):
        """Deutsch fallibilism: posterior must never reach exact 1.0."""
        posterior_high, _ = compute_posterior(prior=1.0, evidence_supports=True)
        assert posterior_high < 1.0, "Fallibilism guard: posterior must be < 1"

    def test_returns_likelihood_in_tuple(self):
        _, likelihood = compute_posterior(prior=0.5, evidence_supports=True)
        assert 0.0 < likelihood <= 1.0


class TestPriorStrategy:
    """C5: Prior strategy auto-selection thresholds."""

    def test_small_history_uses_max_entropy(self):
        strategy, _ = select_prior_strategy(prior_provided=False, calibration_history_size=5)
        assert strategy == "max_entropy"

    def test_at_boundary_still_max_entropy(self):
        strategy, _ = select_prior_strategy(
            prior_provided=False,
            calibration_history_size=PRIOR_EMPIRICAL_MIN - 1,
        )
        assert strategy == "max_entropy"

    def test_sufficient_history_uses_empirical_bayes(self):
        strategy, _ = select_prior_strategy(
            prior_provided=False,
            calibration_history_size=PRIOR_EMPIRICAL_MIN,
        )
        assert strategy == "empirical_bayes"

    def test_large_history_uses_empirical_bayes(self):
        strategy, _ = select_prior_strategy(prior_provided=False, calibration_history_size=50)
        assert strategy == "empirical_bayes"

    def test_user_prior_uses_domain(self):
        strategy, _ = select_prior_strategy(prior_provided=True, calibration_history_size=0)
        assert strategy == "domain"

    def test_empirical_bayes_prior_mean_of_history(self):
        history = [0.6, 0.8, 0.4]
        result = empirical_bayes_prior(history)
        assert abs(result - (0.6 + 0.8 + 0.4) / 3) < 1e-6

    def test_empirical_bayes_empty_history_returns_half(self):
        assert empirical_bayes_prior([]) == 0.5


def _make_cal(posterior: float, tier: str) -> CalibrationResult:
    return CalibrationResult(
        claim_text="test",
        prior=0.5,
        likelihood=0.8,
        posterior=posterior,
        confidence_tier=tier,  # type: ignore[arg-type]
        prior_strategy="max_entropy",
    )


class TestECE:
    def test_ece_empty_history_returns_none(self):
        result = compute_ece([])
        assert result.ece is None

    def test_ece_returns_float_with_history(self):
        history = [_make_cal(0.8, "HIGH"), _make_cal(0.3, "LOW")]
        result = compute_ece(history)
        assert isinstance(result.ece, float)
        assert 0.0 <= result.ece <= 1.0

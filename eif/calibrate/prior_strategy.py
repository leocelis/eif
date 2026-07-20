"""Prior strategy selection for Bayesian calibration."""

from __future__ import annotations

from eif.schemas import PRIOR_EMPIRICAL_MIN, PriorStrategy


def select_prior_strategy(
    prior_provided: bool,
    calibration_history_size: int,
) -> tuple[PriorStrategy, float]:
    """Select prior strategy and return (strategy, prior_value).

    Selection rules:
      - "domain" if user provides a prior (prior_provided=True)
      - "empirical_bayes" if history >= PRIOR_EMPIRICAL_MIN (= 10)
      - "max_entropy" otherwise (uniform prior = 0.5)

    Returns a (strategy, prior_value) where prior_value is 0.5 for max_entropy
    and empirical_bayes (caller must supply the actual value for domain).
    """
    if prior_provided:
        return "domain", 0.5  # caller provides actual value

    if calibration_history_size >= PRIOR_EMPIRICAL_MIN:
        return "empirical_bayes", 0.5

    return "max_entropy", 0.5


def empirical_bayes_prior(history_posteriors: list[float]) -> float:
    """Estimate empirical Bayes prior from calibration history.

    Simple hyperparameter estimation: mean of past posteriors.
    """
    if not history_posteriors:
        return 0.5
    return sum(history_posteriors) / len(history_posteriors)

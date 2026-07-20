"""Sequential Bayesian posterior update."""

from __future__ import annotations

from eif.calibrate.bayesian import compute_posterior


def sequential_update(
    prior_posterior: float,
    evidence_supports: bool,
    likelihood_estimate: float | None = None,
) -> tuple[float, float]:
    """Apply one round of Bayesian update.

    Treats the prior_posterior as P(H) for the next update cycle.
    Returns (new_posterior, likelihood_used).
    """
    if not (0.0 <= prior_posterior <= 1.0):
        raise ValueError(f"prior_posterior must be in [0, 1], got {prior_posterior}")

    return compute_posterior(prior_posterior, evidence_supports, likelihood_estimate)

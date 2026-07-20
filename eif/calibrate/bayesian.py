"""Bayesian posterior computation: P(H|E) = P(E|H) * P(H) / P(E).

Fallibilism constraint (Deutsch): posteriors are bounded to (ε, 1-ε) so that
no claim is ever treated as absolutely certain or absolutely impossible.
Absolute certainty would mean no further evidence could change the belief - 
a violation of scientific fallibilism.
"""

from __future__ import annotations

# Minimum distance from 0 and 1 - Deutsch fallibilism bound
# A claim with posterior 0.9999 is "very likely" not "proven"; 0.0001 is
# "very unlikely" not "impossible". Both remain open to revision.
_FALLIBILISM_EPS: float = 1e-6


def compute_posterior(
    prior: float,
    evidence_supports: bool,
    likelihood_estimate: float | None = None,
) -> tuple[float, float]:
    """Compute Bayesian posterior given prior and evidence.

    P(H|E) = P(E|H) * P(H) / P(E)

    P(E) is computed via total probability:
      P(E) = P(E|H) * P(H) + P(E|¬H) * P(¬H)

    Args:
        prior: P(H) - prior probability of the hypothesis
        evidence_supports: True if evidence supports H, False if it contradicts
        likelihood_estimate: P(E|H) - override if known; defaults to 0.8/0.2

    Returns:
        (posterior, likelihood) tuple
    """
    if likelihood_estimate is not None:
        p_e_given_h = likelihood_estimate
    else:
        p_e_given_h = 0.8 if evidence_supports else 0.2

    p_e_given_not_h = 1.0 - p_e_given_h

    p_e = p_e_given_h * prior + p_e_given_not_h * (1.0 - prior)

    if p_e == 0:
        return prior, p_e_given_h

    posterior = (p_e_given_h * prior) / p_e
    # Fallibilism bound: never allow exact 0 or 1 (C4: posterior in open interval (0,1))
    posterior = max(_FALLIBILISM_EPS, min(1.0 - _FALLIBILISM_EPS, posterior))

    return posterior, p_e_given_h

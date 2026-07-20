"""Sequential Probability Ratio Test (SPRT) - POPPER orientation.

H₀ = claim IS TRUE  (what we want to support; rejecting H₀ means falsified)
H₁ = claim IS FALSE (what we want to detect)

Decision rules:
  Λₖ ≥ B = (1-β)/α  → REJECT H₀ → claim is FALSIFIED
  Λₖ ≤ A = β/(1-α)  → ACCEPT H₀ → claim is tentatively supported
  A < Λₖ < B         → CONTINUE  → gather more observations
"""

from __future__ import annotations

import logging
import math

from eif.schemas import FalsificationCondition, SPRTResult

_log = logging.getLogger(__name__)


def run_sprt(
    fc: FalsificationCondition,
    observations: list[bool],
) -> SPRTResult:
    """Run SPRT on a list of boolean observations.

    Each observation True = claim holds for this sample.
    Each observation False = claim fails for this sample.

    In the POPPER orientation, False observations are evidence for H₁
    (claim is false), pushing Λₖ upward toward REJECT.
    """
    alpha = fc.sprt_alpha
    beta = fc.sprt_beta
    effect_size = fc.sprt_effect_size

    accept_boundary = beta / (1 - alpha)
    reject_boundary = (1 - beta) / alpha

    # Under H₀ (claim is TRUE): P(obs=True | H₀) = p₀, P(obs=False | H₀) = 1 - p₀
    # Under H₁ (claim is FALSE): P(obs=True | H₁) = p₁, P(obs=False | H₁) = 1 - p₁
    # We model: p₀ = 0.5 + effect_size/2 (favorable under H₀)
    #            p₁ = 0.5 - effect_size/2 (unfavorable under H₁)
    p0 = min(0.5 + effect_size / 2, 0.99)
    p1 = max(0.5 - effect_size / 2, 0.01)

    log_lambda = 0.0
    for obs in observations:
        if obs:
            # P(obs=True | H₁) / P(obs=True | H₀)
            log_lambda += math.log(p1 / p0)
        else:
            # P(obs=False | H₁) / P(obs=False | H₀)
            log_lambda += math.log((1 - p1) / (1 - p0))

    lambda_k = math.exp(log_lambda)

    if lambda_k >= reject_boundary:
        decision = "REJECT"
        stopped_early = True
    elif lambda_k <= accept_boundary:
        decision = "ACCEPT"
        stopped_early = True
    else:
        decision = "CONTINUE"
        stopped_early = False

    _log.debug(
        "SPRT  decision=%s  Λₖ=%.4f  A=%.4f  B=%.4f  n=%d",
        decision, lambda_k, accept_boundary, reject_boundary, len(observations),
    )

    return SPRTResult(
        decision=decision,
        likelihood_ratio=lambda_k,
        observations_count=len(observations),
        alpha=alpha,
        beta=beta,
        accept_boundary=accept_boundary,
        reject_boundary=reject_boundary,
        stopped_early=stopped_early,
        claim_text=fc.claim_text,  # carry claim identity for compliance report listings
    )

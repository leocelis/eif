"""Priority scoring for hypothesis agenda - Bayesian EIG-based ranking.

Formula (from intent HA1–HA6):
    priority(claim) = EIG(prior, posterior)
                      × consequence_weight
                      × boundary_factor
                      × uncertainty_factor

Where:
    EIG            - KL divergence (information already gained from prior→posterior)
                     inverted: high EIG means the claim is already well-informed,
                     so we use (1 - normalized_eig) as uncertainty proxy.
                     For unprobed GUESSED/ASSUMED claims with flat prior, EIG=0
                     meaning maximum uncertainty → highest value to probe.
    consequence_weight - HIGH=3.0, MEDIUM=1.5, LOW=1.0
    boundary_factor    - Gaussian proximity to nearest decision threshold
                         (ACT=0.70 or HALT=0.20). Claims near a threshold are
                         decision-critical: small evidence shift flips routing.
    uncertainty_factor - GUESSED=1.5, ASSUMED=1.2, KNOWN=0.5

Research: Chaloner & Verdinelli (1995); GRACE (2025); LAPD (2025)
"""

from __future__ import annotations

import math

from eif.schemas import (
    THRESHOLD_ACT,
    THRESHOLD_HALT,
    Claim,
    ClaimType,
    RiskLevel,
)

# Consequence weights - maps RiskLevel to numeric multiplier
_CONSEQUENCE_WEIGHT: dict[RiskLevel, float] = {
    "HIGH": 3.0,
    "MEDIUM": 1.5,
    "LOW": 1.0,
}

# Uncertainty factors - GUESSED has most to gain from testing
_UNCERTAINTY_FACTOR: dict[ClaimType, float] = {
    "GUESSED": 1.5,
    "ASSUMED": 1.2,
    "KNOWN": 0.5,
}

# Boundary Gaussian width (σ²) - narrower = only very-near-threshold claims score high
_BOUNDARY_SIGMA_SQ: float = 0.05

# Default posterior for unprobed claims (flat prior)
_DEFAULT_POSTERIOR_BY_TYPE: dict[ClaimType, float] = {
    "GUESSED": 0.35,
    "ASSUMED": 0.55,
    "KNOWN": 0.80,
}


def compute_consequence_weight(risk: RiskLevel) -> float:
    return _CONSEQUENCE_WEIGHT[risk]


def compute_uncertainty_factor(claim_type: ClaimType) -> float:
    return _UNCERTAINTY_FACTOR[claim_type]


def compute_boundary_factor(posterior: float) -> float:
    """Gaussian proximity to nearest decision threshold.

    Returns value in [0, 1].  Peak = 1.0 when posterior == threshold.
    constraint HA2: posterior within ±0.10 of a threshold → factor ≥ 0.60.

    Both ACT (0.70) and HALT (0.20) are checked; the closer threshold wins.
    """
    dist_act = abs(posterior - THRESHOLD_ACT)
    dist_halt = abs(posterior - THRESHOLD_HALT)
    nearest_dist = min(dist_act, dist_halt)
    return math.exp(-(nearest_dist ** 2) / _BOUNDARY_SIGMA_SQ)


def nearest_threshold(posterior: float) -> float:
    dist_act = abs(posterior - THRESHOLD_ACT)
    dist_halt = abs(posterior - THRESHOLD_HALT)
    return THRESHOLD_ACT if dist_act <= dist_halt else THRESHOLD_HALT


def compute_residual_eig(posterior: float, claim_type: ClaimType) -> float:
    """Estimate the Expected Information Gain from running a test on this claim.

    We model this as the KL divergence from the type-default prior to the
    current posterior - but *inverted*: a posterior already far from the prior
    means the claim has already been well-characterised. A posterior near the
    type-default prior means maximum residual uncertainty, i.e. most to gain
    from testing.

    Type-default priors: GUESSED=0.35, ASSUMED=0.55, KNOWN=0.80
    (from _DEFAULT_POSTERIOR_BY_TYPE - not the flat 0.50 prior).

    residual_eig ∝ 1 − KL(posterior ∥ type_prior) / KL_max

    KL_max ≈ 0.693 (KL when posterior = 0 or 1 vs prior = 0.50).
    """
    from eif.update.eig import compute_eig

    prior = _DEFAULT_POSTERIOR_BY_TYPE[claim_type]
    raw_eig = compute_eig(prior=prior, posterior=posterior)
    kl_max = 0.693
    # Residual = how much uncertainty remains (inverse of information already gained)
    residual = max(0.0, 1.0 - raw_eig / kl_max)
    return residual


def compute_priority_score(
    claim: Claim,
    current_posterior: float | None = None,
) -> tuple[float, float, float, float, float]:
    """Compute priority score for a single claim.

    Returns:
        (priority_score, eig_score, consequence_weight, boundary_factor, uncertainty_factor)
    """
    posterior = current_posterior if current_posterior is not None else _DEFAULT_POSTERIOR_BY_TYPE[claim.claim_type]

    eig_score = compute_residual_eig(posterior, claim.claim_type)
    c_weight = compute_consequence_weight(claim.consequence_of_wrong)
    b_factor = compute_boundary_factor(posterior)
    u_factor = compute_uncertainty_factor(claim.claim_type)

    priority = eig_score * c_weight * b_factor * u_factor
    return priority, eig_score, c_weight, b_factor, u_factor

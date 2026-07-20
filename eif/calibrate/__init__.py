"""EIF Phase 3 - CALIBRATE: Bayesian posterior computation."""

from eif.calibrate.bayesian import compute_posterior
from eif.calibrate.conformal import compute_conformal_coverage
from eif.calibrate.ece import compute_ece
from eif.calibrate.prior_strategy import select_prior_strategy
from eif.calibrate.trust import tier_confidence_likelihood

__all__ = [
    "compute_posterior",
    "compute_ece",
    "compute_conformal_coverage",
    "select_prior_strategy",
    "tier_confidence_likelihood",
]

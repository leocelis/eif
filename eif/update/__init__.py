"""EIF Phase 5 - UPDATE: sequential Bayesian update with stopping rules."""

from eif.update.eig import compute_eig
from eif.update.paradigm import PARADIGM_ALERT_THRESHOLD, check_paradigm_revision
from eif.update.posterior import sequential_update
from eif.update.stopping import evaluate_stopping

__all__ = [
    "sequential_update",
    "compute_eig",
    "evaluate_stopping",
    "check_paradigm_revision",
    "PARADIGM_ALERT_THRESHOLD",
]

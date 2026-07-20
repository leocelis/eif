"""Conformal prediction coverage computation - V2 label-grounded.

V1 used confidence_tier (HIGH/MEDIUM/LOW) as a proxy for actual outcomes.
V2 uses real binary outcomes (outcome_history) when available (F1C1 analogy).

Research:
  Conformal prediction arXiv:2107.07511 (Angelopoulos & Bates) - 
    P(y_true ∈ C(x)) ≥ 1 − α; distribution-free coverage guarantee.
  Black-box agent conformal arXiv:2602.21368 (2026) - 
    self-consistency sampling + conformal calibration for AI agents.
"""

from __future__ import annotations

import math

from eif.schemas import CONFORMAL_MIN_HISTORY, CalibrationResult


def compute_conformal_coverage(
    history: list[CalibrationResult],
    outcome_history: list[bool | None] | None = None,
    alpha: float = 0.05,
) -> float | None:
    """Compute conformal prediction coverage.

    Algorithm:
    1. Collect nonconformity scores: score_i = |posterior_i - actual_outcome_i|
       When outcome_history contains non-None values, real binary labels are used;
       otherwise the tier-proxy fallback applies.
    2. Compute quantile q = sorted_scores[ceil((n+1)(1-alpha))]
    3. conformal_coverage = 1 - (# scores above q) / n

    Returns None when fewer than CONFORMAL_MIN_HISTORY calibration points exist.
    """
    if len(history) < CONFORMAL_MIN_HISTORY:
        return None

    tier_to_outcome = {"HIGH": 1.0, "MEDIUM": 0.5, "LOW": 0.0}

    scores: list[float] = []
    for i, r in enumerate(history):
        if outcome_history and i < len(outcome_history) and outcome_history[i] is not None:
            actual = 1.0 if outcome_history[i] else 0.0
        else:
            actual = tier_to_outcome.get(r.confidence_tier, 0.5)
        scores.append(abs(r.posterior - actual))

    n = len(scores)
    sorted_scores = sorted(scores)

    idx = math.ceil((n + 1) * (1 - alpha)) - 1
    idx = min(idx, n - 1)
    q = sorted_scores[idx]

    above_q = sum(1 for s in scores if s > q)
    return 1.0 - above_q / n

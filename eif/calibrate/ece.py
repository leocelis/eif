"""Expected Calibration Error (ECE) computation - V2 label-grounded.

V1 used confidence_tier (HIGH/MEDIUM/LOW) as a proxy for observed outcomes.
V2 replaces that proxy with real binary outcomes when ≥ 30 labeled (posterior, outcome)
pairs are available for the session (F1C1). Below that threshold the tier-proxy is
retained with an explicit UNCALIBRATED warning (F1C2).

Domain-specific posterior ceilings (F1C3 - Physics-Informed Metacognition) are
defined in domain_constraints.py with full regulatory provenance. Import
DOMAIN_POSTERIOR_CEILINGS from there rather than duplicating values here.

Research:
  HALoGEN arXiv:2501.08292 (ACL 2025 Outstanding Paper) - up to 86% hallucination;
  high confidence does NOT reliably correlate with accuracy without label evidence.
  Conformal prediction arXiv:2107.07511 - standard ECE formula.
  Physics-Informed Metacognition OpenReview LF4RSTZUtA (2025) - 37.2% ECE
  reduction from domain-constraint embedding; basis for apply_domain_ceiling().
"""

from __future__ import annotations

from eif.calibrate.domain_constraints import DOMAIN_POSTERIOR_CEILINGS
from eif.schemas import CalibrationResult, ECEResult

# Minimum labeled-outcome history to switch from tier-proxy to real ECE (F1C2)
ECE_LABEL_MIN: int = 30


def _tier_to_outcome(tier: str) -> float:
    return {"HIGH": 1.0, "MEDIUM": 0.5, "LOW": 0.0}.get(tier, 0.5)


def _ece_from_bins(
    posteriors: list[float],
    outcomes: list[float],
    n_bins: int = 10,
) -> float:
    """Standard ECE = Σ_b (|B_b|/n) * |acc(B_b) - conf(B_b)|."""
    n = len(posteriors)
    if n == 0:
        return 0.0

    bin_size = 1.0 / n_bins
    ece = 0.0
    for b in range(n_bins):
        lo, hi = b * bin_size, (b + 1) * bin_size
        indices = [i for i, p in enumerate(posteriors) if lo <= p < hi]
        if not indices:
            continue
        avg_conf = sum(posteriors[i] for i in indices) / len(indices)
        avg_acc = sum(outcomes[i] for i in indices) / len(indices)
        ece += (len(indices) / n) * abs(avg_acc - avg_conf)

    return round(ece, 6)


def compute_ece(
    history: list[CalibrationResult],
    outcome_history: list[bool | None] | None = None,
    n_bins: int = 10,
) -> ECEResult:
    """Compute ECE using real outcomes when available (F1C1/F1C2).

    Args:
        history:         CalibrationResult objects from the session.
        outcome_history: Optional parallel list of bool | None. True = correct,
                         False = incorrect, None = not yet observed. When provided
                         and ≥ ECE_LABEL_MIN values are non-None, label-grounded
                         ECE is computed. Otherwise falls back to tier proxy.
        n_bins:          Number of equal-width calibration bins.

    Returns:
        ECEResult with label_grounded flag and optional calibration_warning.
    """
    if not history:
        return ECEResult(ece=None, label_grounded=False, sessions_used=0)

    # Collect labeled pairs
    labeled: list[tuple[float, float]] = []
    if outcome_history:
        for r, obs in zip(history, outcome_history, strict=False):
            if obs is not None:
                labeled.append((r.posterior, 1.0 if obs else 0.0))

    if len(labeled) >= ECE_LABEL_MIN:
        # F1C1 - label-grounded path
        posteriors = [p for p, _ in labeled]
        outcomes = [o for _, o in labeled]
        ece_val = _ece_from_bins(posteriors, outcomes, n_bins)
        return ECEResult(
            ece=ece_val,
            label_grounded=True,
            sessions_used=len(labeled),
        )

    # F1C2 - tier-proxy fallback with UNCALIBRATED warning
    # Use all calibration history rows for the tier-proxy computation but
    # report sessions_used=len(labeled) so the field consistently reflects
    # "how many real (posterior, outcome) pairs were available" in both modes.
    n_history = len(history)
    posteriors = [r.posterior for r in history]
    outcomes = [_tier_to_outcome(r.confidence_tier) for r in history]
    ece_val = _ece_from_bins(posteriors, outcomes, n_bins)
    warning = (
        "UNCALIBRATED: ECE is a confidence-tier proxy "
        f"({n_history} calibration row(s) used; tier proxy active). "
        "Provide outcome feedback via eif_record_outcome to enable label-grounded calibration "
        f"({len(labeled)}/{ECE_LABEL_MIN} labeled (posterior, outcome) pairs available)."
    )
    return ECEResult(
        ece=ece_val,
        label_grounded=False,
        sessions_used=len(labeled),  # R11-07: consistent semantics - labeled pairs, not history rows
        calibration_warning=warning,
    )


def apply_domain_ceiling(
    posterior: float,
    domain: str,
    evidence_tier: str | None = None,
) -> tuple[float, bool]:
    """F1C3: Physics-Informed Metacognition - clamp posteriors by domain.

    Healthcare/engineering domains enforce posterior ceilings unless the
    evidence tier is a DIRECT-OBSERVATION tier - P1 (native code execution) or
    P2 (experiment / RCT-category). Parametric (P4) and web-search (P3) sources
    alone cannot push a regulated-domain claim above its ceiling.

    TW6 (eif_v5_evidence_trust_weighting): P3 web evidence is now SUBJECT to the
    ceiling. Web text is not direct observation - it is the corpus an attacker can
    poison (PoisonedRAG arXiv:2402.07867) and the noisy channel that degrades RAG
    accuracy (The Power of Noise arXiv:2401.14887). Only direct-observation tiers
    (P1/P2) - and authoritative host tools (P0), which are not regulated-domain
    proxies - may exceed a regulated-domain ceiling. This narrows the prior F1C3
    bypass tuple from (P1, P2, P3) to (P1, P2).

    Returns:
        (clamped_posterior, domain_clamp_applied)
    """
    ceiling = DOMAIN_POSTERIOR_CEILINGS.get(domain.lower())
    if ceiling is None:
        return posterior, False

    # Only direct-observation tiers P1 (native code) and P2 (rct/meta-analysis
    # category) may reach the ceiling. P3 (web search) and P4 (parametric LLM)
    # cannot exceed it - TW6.
    if evidence_tier in ("P1_NATIVE_CODE", "P2_EXPERIMENTAL"):
        return posterior, False

    if posterior > ceiling:
        return ceiling, True

    return posterior, False

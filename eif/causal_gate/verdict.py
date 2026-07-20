"""CAUSAL_GATE v4 - posterior adjustment for CausalEvidenceVerdict.

Maps each CEP verdict to a posterior delta and provides helpers for
applying the adjustment. Deltas are calibrated to match FALSIFY's
existing SUPPORTS/CONTRADICTS magnitudes for consistency.

Research basis:
  CG4 (intent v1.0): SUPPORTED +0.15, NO_EVIDENCE 0.0, CONTESTED -0.20, REVERSED -0.35
  The REVERSED delta (-0.35) intentionally matches FALSIFY CONTRADICTS magnitude.
"""

from __future__ import annotations

from eif.schemas import CausalEvidenceVerdict

# Posterior deltas per verdict (CG4 constraint)
VERDICT_POSTERIOR_DELTA: dict[str, float] = {
    "SUPPORTED": +0.15,
    "NO_EVIDENCE": 0.0,
    "CONTESTED": -0.20,
    "REVERSED": -0.35,
}


def posterior_delta(verdict: CausalEvidenceVerdict) -> float:
    """Return the posterior adjustment for a given CEP verdict."""
    return VERDICT_POSTERIOR_DELTA.get(verdict, 0.0)


def apply_verdict_to_posterior(prior: float, verdict: CausalEvidenceVerdict) -> float:
    """Apply the verdict delta to a prior probability, clamped to [0.0, 1.0]."""
    return max(0.0, min(1.0, prior + posterior_delta(verdict)))


def provenance_flag_for(
    verdict: CausalEvidenceVerdict,
    consequence: str,
) -> str | None:
    """Return 'CAUSAL_UNVERIFIED' when NO_EVIDENCE on a HIGH-consequence claim.

    Satisfies EU AI Act Art. 9 (risk management documentation - CG6).
    Returns None in all other cases so the flag is absent from provenance
    for claims that were verified.
    """
    if verdict == "NO_EVIDENCE" and consequence == "HIGH":
        return "CAUSAL_UNVERIFIED"
    return None

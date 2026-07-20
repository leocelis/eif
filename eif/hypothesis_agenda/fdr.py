"""FDR correction annotation for HYPOTHESIS_AGENDA.

When EIF tests N claims in a single session it implicitly runs N hypothesis
tests. Standard FDR control (Benjamini & Hochberg 1995) applies: the expected
false-discovery rate rises with N.  Because the test set is search-generated
(not pre-specified), classical corrections don't fully apply - but the
multiplicity risk must be surfaced.

Intent note: eif_hypothesis_agenda_intent.yaml HA2 governs boundary_factor
(claims near decision thresholds ≥ 0.60), not FDR annotation. FDR annotation
here is an additional multiplicity safeguard without a separate HA* constraint;
add one if FDR thresholds need to be formally tested.

Research: frontier_debates.md §6 (citing B&H 1995); statistics.md FDR entry.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Thresholds ────────────────────────────────────────────────────────────────

_FDR_HIGH_N: int = 10    # N > 10 → HIGH inflation risk; warn strongly
_FDR_MED_N: int = 5      # N > 5  → MEDIUM inflation risk; note it

FDRInflationRisk = str  # "LOW" | "MEDIUM" | "HIGH"


# ── Public API ────────────────────────────────────────────────────────────────

@dataclass
class FDRAdjustment:
    """FDR annotation for a single claim in the agenda."""
    rank: int                          # 1-based rank
    alpha_adjusted: float              # Benjamini-Hochberg adjusted threshold
    inflation_risk: FDRInflationRisk   # LOW / MEDIUM / HIGH


def apply_fdr_correction(
    total_claims: int,
    alpha: float = 0.05,
) -> tuple[list[FDRAdjustment], str | None]:
    """Compute BH-adjusted thresholds for a ranked agenda of N claims.

    Benjamini & Hochberg (1995): α_adjusted(k) = (k / N) × α, for rank k
    in a sorted list (rank 1 = most important, rank N = least).

    Because the test set is search-generated (not pre-specified), we annotate
    rather than filter - the inflation_risk guides the caller on how to
    interpret results, not which claims to drop.

    Args:
        total_claims: number of claims in the agenda (N).
        alpha:        nominal significance level (default 0.05).

    Returns:
        (adjustments, fdr_warning)
        adjustments: one FDRAdjustment per rank (rank 1 … N).
        fdr_warning: plain-language warning string when N > _FDR_MED_N, else None.
    """
    n = max(1, total_claims)

    if n <= _FDR_MED_N:
        risk = "LOW"
    elif n <= _FDR_HIGH_N:
        risk = "MEDIUM"
    else:
        risk = "HIGH"

    adjustments: list[FDRAdjustment] = [
        FDRAdjustment(
            rank=k,
            alpha_adjusted=round((k / n) * alpha, 6),
            inflation_risk=risk,
        )
        for k in range(1, n + 1)
    ]

    fdr_warning: str | None = None
    if risk == "HIGH":
        fdr_warning = (
            f"FDR WARNING: {n} claims tested - false discovery rate is elevated. "
            f"Prioritize the top-2 items only; treat remaining verdicts as exploratory. "
            f"(Benjamini & Hochberg 1995; frontier_debates.md §6)"
        )
    elif risk == "MEDIUM":
        fdr_warning = (
            f"FDR NOTE: {n} claims tested - moderate multiple-comparisons risk. "
            f"Treat lower-ranked verdicts as indicative, not conclusive."
        )

    return adjustments, fdr_warning

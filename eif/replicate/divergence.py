"""Evaluate replication results and compute agreement rate."""

from __future__ import annotations

from eif.schemas import REPLICATE_AGREE_THRESHOLD, REPLICATE_FAIL_THRESHOLD


def _semantic_match(result: str, original_claim: str) -> bool:
    """Simple heuristic: check if key terms from the claim appear in the result."""
    claim_tokens = set(original_claim.lower().split())
    result_tokens = set(result.lower().split())
    if not claim_tokens:
        return False
    overlap = len(claim_tokens & result_tokens) / len(claim_tokens)
    return overlap > 0.3


def evaluate_replication(
    claim_text: str,
    replication_results: list[str],
    replication_criterion: str = "STATISTICAL",
    replication_type: str = "REPRODUCIBILITY",
) -> tuple[str, float, list[str]]:
    """Evaluate replication results and return (verdict, agreement_rate, divergence_details).

    Agreement is computed as the ratio of results that semantically match the claim.
    Thresholds:
      REPLICATED   >= REPLICATE_AGREE_THRESHOLD (0.80)
      INCONCLUSIVE  REPLICATE_FAIL_THRESHOLD <= x < REPLICATE_AGREE_THRESHOLD (0.50-0.80)
      DIVERGED     < REPLICATE_FAIL_THRESHOLD (0.50)
    """
    if not replication_results:
        return "INCONCLUSIVE", 0.0, []

    matches = [_semantic_match(r, claim_text) for r in replication_results]
    agreement_rate = sum(matches) / len(matches)

    divergence_details = [
        f"Replicate {i+1} diverged: {r[:100]}"
        for i, (r, matched) in enumerate(zip(replication_results, matches, strict=False))
        if not matched
    ]

    if agreement_rate >= REPLICATE_AGREE_THRESHOLD:
        verdict = "REPLICATED"
    elif agreement_rate < REPLICATE_FAIL_THRESHOLD:
        verdict = "DIVERGED"
    else:
        verdict = "INCONCLUSIVE"

    return verdict, agreement_rate, divergence_details

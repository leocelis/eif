"""Generate replication protocol text."""

from __future__ import annotations

from eif.schemas import REPLICATE_AGREE_THRESHOLD, REPLICATE_FAIL_THRESHOLD

_REPLICATION_TYPE_MAP = {
    "SELF_CONSISTENCY": "REPRODUCIBILITY",
    "INDEPENDENT_SAMPLE": "REPLICABILITY",
    "INDEPENDENT": "REPLICABILITY",  # alias accepted by eif_replicate tool description
}


def get_replication_type(isolation_strategy: str) -> str:
    """Map isolation_strategy to replication type label."""
    return _REPLICATION_TYPE_MAP.get(isolation_strategy, "REPRODUCIBILITY")


def generate_replication_protocol(
    claim_text: str,
    original_inputs: dict,
    isolation_strategy: str = "SELF_CONSISTENCY",
    n_replicates: int = 3,
    replication_criterion: str = "STATISTICAL",
) -> tuple[str, str]:
    """Generate a replication protocol text.

    Returns:
        (protocol_text, replication_type)
        replication_type is REPRODUCIBILITY (SELF_CONSISTENCY) or REPLICABILITY (INDEPENDENT_SAMPLE)
    """
    if n_replicates < 2:
        raise ValueError(f"n_replicates must be >= 2, got {n_replicates}")

    replication_type = get_replication_type(isolation_strategy)

    if isolation_strategy == "SELF_CONSISTENCY":
        strategy_description = (
            "REPRODUCIBILITY test: same inputs, same model, independent samples.\n"
            "Tests that the claim is stable (not a sampling artifact).\n"
            "Does NOT test generalization beyond original conditions."
        )
    else:
        strategy_description = (
            "REPLICABILITY test: different inputs/context, new execution.\n"
            "Tests whether the same conclusion holds under new conditions.\n"
            "This is the stronger test - analogous to human scientific replication."
        )

    protocol = (
        f"REPLICATION PROTOCOL ({replication_type})\n"
        f"{'=' * 50}\n\n"
        f"Claim: {claim_text!r}\n\n"
        f"Strategy: {strategy_description}\n\n"
        f"Original inputs: {original_inputs}\n\n"
        f"Steps:\n"
        f"1. Run {n_replicates} independent replication attempts.\n"
        f"2. For each attempt, apply the original inputs "
        f"{'exactly as-is' if isolation_strategy == 'SELF_CONSISTENCY' else 'with varied context'}.\n"
        f"3. Record the output for each attempt.\n"
        f"4. Compare outputs against the original claim using criterion: {replication_criterion}\n\n"
        f"Verdict criteria:\n"
        f"  REPLICATED   = agreement_rate >= {REPLICATE_AGREE_THRESHOLD}\n"
        f"  INCONCLUSIVE = {REPLICATE_FAIL_THRESHOLD} <= agreement_rate < {REPLICATE_AGREE_THRESHOLD}\n"
        f"  DIVERGED     = agreement_rate < {REPLICATE_FAIL_THRESHOLD}"
    )

    return protocol, replication_type

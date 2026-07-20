"""Stopping rule evaluation for the UPDATE phase."""

from __future__ import annotations

from eif.schemas import (
    EIG_THRESHOLD,
    SPRTResult,
    StoppingReason,
)


def evaluate_stopping(
    eig: float,
    sprt_result: SPRTResult | None = None,
    decision_value: float | None = None,
    cost_estimate: float | None = None,
    delta_min: float = EIG_THRESHOLD,
) -> tuple[bool, StoppingReason | None]:
    """Evaluate stopping rules (in priority order).

    Rules - only those whose inputs are provided are evaluated:
    1. EIG < delta_min → EIG_BELOW_THRESHOLD (always evaluated)
    2. sprt_result is not None AND decision != CONTINUE → SPRT_BOUNDARY
    3. decision_value and cost_estimate are both not None AND cost > value → COST_EXCEEDS_VALUE

    Note: eif_update only passes `eig` and `delta_min`, so only rule 1 can fire
    on that tool path. Rules 2 and 3 are available to the eif_verify pipeline and
    direct Python callers that supply the optional arguments.

    Returns (triggered, reason).
    """
    if eig < delta_min:
        return True, "EIG_BELOW_THRESHOLD"

    if sprt_result is not None and sprt_result.decision != "CONTINUE":
        return True, "SPRT_BOUNDARY"

    if decision_value is not None and cost_estimate is not None:
        if cost_estimate > decision_value:
            return True, "COST_EXCEEDS_VALUE"

    return False, None

"""Build FalsificationCondition objects."""

from __future__ import annotations

from datetime import datetime

from eif.falsify.hard_to_vary import check_hard_to_vary
from eif.falsify.trivial_check import is_trivial
from eif.schemas import FalsificationCondition


def build_condition(
    claim_text: str,
    condition: str,
    threshold: str,
    test_procedure: str,
    alpha: float = 0.05,
    beta: float = 0.10,
    effect_size: float = 0.2,
) -> FalsificationCondition:
    """Construct and validate a FalsificationCondition.

    Runs two checks:
      1. is_trivial() - catches vacuously satisfiable conditions
         (always/never/any/0%/100%).
      2. check_hard_to_vary() - catches conditions with vague threshold,
         vague procedure, or adjustable language (Deutsch criterion, §4.2b).

    trivial_flag=True when EITHER check fires. hard_to_vary_reasons contains
    specific dimension-level feedback from check_hard_to_vary when it fires.
    registered_at is always set to datetime.utcnow() at construction time.
    """
    if not condition:
        raise ValueError("condition cannot be empty")
    if not threshold:
        raise ValueError("threshold cannot be empty")
    if not test_procedure:
        raise ValueError("test_procedure cannot be empty")
    if not (0 < alpha < 1):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    if not (0 < beta < 1):
        raise ValueError(f"beta must be in (0, 1), got {beta}")

    trivial = is_trivial(condition, threshold)
    htv_vague, htv_reasons = check_hard_to_vary(condition, threshold, test_procedure)

    return FalsificationCondition(
        claim_text=claim_text,
        condition=condition,
        threshold=threshold,
        test_procedure=test_procedure,
        sprt_alpha=alpha,
        sprt_beta=beta,
        sprt_effect_size=effect_size,
        trivial_flag=trivial or htv_vague,
        hard_to_vary_reasons=htv_reasons,
        registered_at=datetime.utcnow(),
    )

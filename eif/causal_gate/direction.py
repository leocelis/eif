"""Check if evidence supports the claimed causal direction."""

from __future__ import annotations


def check_direction(
    cause_variable: str,
    effect_variable: str,
    evidence_text: str,
) -> bool:
    """Return True if the cause appears before the effect in the evidence text.

    This is a simple heuristic: temporal ordering in text often reflects
    causal ordering. A cause mentioned before its effect is consistent with
    the claimed direction.
    """
    cause_lower = cause_variable.lower()
    effect_lower = effect_variable.lower()
    text_lower = evidence_text.lower()

    cause_pos = text_lower.find(cause_lower)
    effect_pos = text_lower.find(effect_lower)

    if cause_pos == -1 or effect_pos == -1:
        # Can't determine direction from text - default to True (undetectable)
        return True

    return cause_pos < effect_pos

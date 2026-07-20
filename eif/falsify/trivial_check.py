"""Detect trivially satisfiable falsification conditions."""

from __future__ import annotations

import re

_TRIVIAL_PHRASES = {
    "always",
    "never fails",
    "always passes",
    "always true",
    "never",
    "any",
    "anything",
    "everything",
}

_TRIVIAL_THRESHOLD_PATTERN = re.compile(
    r"^\s*(any|anything|none|n/a|na|not applicable|0%|100%|always|never)\s*$",
    re.IGNORECASE,
)


def is_trivial(condition: str, threshold: str) -> bool:
    """Return True if this falsification condition is trivially satisfiable.

    A condition is trivial when:
    - The condition text contains phrases like "always", "never fails"
    - The threshold is empty, "any", "never", or other non-specific values
    - The condition text is empty (already caught upstream, but guard here too)
    """
    if not condition.strip():
        return True

    condition_lower = condition.strip().lower()
    for phrase in _TRIVIAL_PHRASES:
        if phrase in condition_lower:
            return True

    if not threshold.strip():
        return True

    if _TRIVIAL_THRESHOLD_PATTERN.match(threshold):
        return True

    return False

"""Classify the reach scope of an explanation (LOCAL vs BROADER)."""

from __future__ import annotations

from eif.schemas import ReachScope

_BROADER_MARKERS = {
    "general",
    "always",
    "any system",
    "universal",
    "all cases",
    "in general",
    "generally",
    "universally",
    "across all",
    "every system",
    "any context",
}


def classify_reach(explanation: str) -> ReachScope:
    """Classify explanation scope as LOCAL or BROADER.

    BROADER if the explanation uses generalizing language.
    LOCAL otherwise (specific to the observed case).
    """
    explanation_lower = explanation.lower()
    for marker in _BROADER_MARKERS:
        if marker in explanation_lower:
            return "BROADER"
    return "LOCAL"

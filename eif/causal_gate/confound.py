"""Confounder detection for causal hypotheses.

Two complementary strategies (IRIS-inspired, arXiv:2510.09217):

1. check_confounders      - verifies that analyst-supplied confounders are
                            acknowledged in the hypothesis text (original).

2. discover_confounders   - actively searches P3 for *unknown* confounders
                            using the cause/effect/domain extracted from the
                            claim. Returns a deduplicated list of confounder
                            candidates not already in the hypothesis.
                            Called unconditionally by eif_causal_gate for all
                            causal levels (not just INTERVENTION/COUNTERFACTUAL);
                            the CEP (CausalEvidenceProbe) is the tier that is
                            gated on HIGH-consequence INTERVENTION/COUNTERFACTUAL.

Research: IRIS (arXiv:2510.09217, ACL 2025) - iterative missing variable
identification from unstructured evidence. Key finding: the confounders most
likely to invalidate a causal claim are the ones *not in the dataset*, not the
ones already named by the analyst.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

_log = logging.getLogger(__name__)

# Search suffix for confounder discovery
_CONFOUNDER_SUFFIX = "confounders mediators alternative explanations spurious correlation"

_EXTRACT_CONFOUNDERS_PROMPT = """\
A researcher claims: "{cause}" causes "{effect}" in the domain of "{domain}".

Based on the following search results, identify confounders, mediators, or
alternative explanations that could invalidate this causal claim:

---
{search_results}
---

Return a JSON array of confounder strings. Each item should be a short phrase
describing a specific variable or mechanism. Maximum 5 items. If no confounders
are identifiable from the results, return [].

Example output: ["selection bias", "socioeconomic status", "publication date effects"]

Return ONLY the JSON array, no commentary.
"""


def check_confounders(
    hypothesis: str,
    potential_confounders: list[str] | None,
) -> list[str]:
    """Return analyst-supplied confounders not acknowledged in the hypothesis.

    A confounder is considered documented if its name appears in the hypothesis
    text. Undocumented confounders are flagged for review.
    """
    if not potential_confounders:
        return []

    hypothesis_lower = hypothesis.lower()
    return [c for c in potential_confounders if c.lower() not in hypothesis_lower]


def discover_confounders(
    cause: str,
    effect: str,
    domain: str,
    hypothesis: str,
    search_fn: Callable[[str], str] | None = None,
    llm_fn: Callable[[str], str] | None = None,
) -> list[str]:
    """Actively discover unknown confounders via P3 search + LLM extraction.

    This implements the IRIS missing variable identification step: search for
    confounders that are not in the current dataset (hypothesis text) but are
    known to the scientific community for this cause→effect relationship.

    Args:
        cause:      extracted cause variable
        effect:     extracted effect variable
        domain:     domain context (e.g. "healthcare", "finance")
        hypothesis: original hypothesis text - used to filter out already-
                    acknowledged confounders from the discovered list
        search_fn:  optional P3 search override (default: DDGS native_search)
        llm_fn:     optional LLM extractor (if None, uses heuristic extraction)

    Returns:
        List of newly-discovered confounder strings, excluding any already
        mentioned in the hypothesis. Empty list if none found or on error.
    """
    query = f"{cause} {effect} {_CONFOUNDER_SUFFIX} {domain}".strip()

    # Run P3 search
    search_results = ""
    try:
        if search_fn is not None:
            search_results = search_fn(query)
        else:
            from eif.falsify.native_tools import native_search  # noqa: PLC0415
            search_results = native_search(query, max_results=5)
    except Exception:  # noqa: BLE001
        _log.debug("discover_confounders: P3 search unavailable - returning []")
        return []

    if not search_results.strip():
        return []

    # Extract confounder candidates
    candidates: list[str] = []
    if llm_fn is not None:
        candidates = _extract_via_llm(cause, effect, domain, search_results, llm_fn)
    else:
        candidates = _extract_heuristic(search_results)

    # Filter out confounders already present in the hypothesis (case-insensitive)
    hypothesis_lower = hypothesis.lower()
    novel = [c for c in candidates if c.lower() not in hypothesis_lower]

    if novel:
        _log.info(
            "IRIS: discovered %d novel confounder(s) for '%s → %s': %s",
            len(novel), cause, effect, novel,
        )

    return novel[:5]


def _extract_via_llm(
    cause: str,
    effect: str,
    domain: str,
    search_results: str,
    llm_fn: Callable[[str], str],
) -> list[str]:
    """Use LLM to extract confounder candidates from search results."""
    import json

    prompt = _EXTRACT_CONFOUNDERS_PROMPT.format(
        cause=cause,
        effect=effect,
        domain=domain,
        search_results=search_results[:3000],
    )
    try:
        raw = llm_fn(prompt)
        json_text = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", raw, flags=re.DOTALL).strip()
        parsed = json.loads(json_text)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if item]
    except Exception:  # noqa: BLE001
        _log.debug("discover_confounders: LLM extraction failed - falling back to heuristic")

    return _extract_heuristic(search_results)


# Common confounder signal phrases used in the heuristic fallback
_CONFOUNDER_SIGNALS = [
    r"confound(?:ed|er|ing)\s+(?:by|with|variable)?\s*([\w\s]{4,40})",
    r"spurious(?:ly)?\s+(?:correlated?|due to)\s*([\w\s]{4,40})",
    r"mediat(?:ed|or|ing)\s+(?:by|through)?\s*([\w\s]{4,40})",
    r"alternative\s+explanation[:\s]+([\w\s]{4,60})",
    r"control(?:led|ling)?\s+for\s+([\w\s]{4,40})",
]
_CONFOUNDER_RE = re.compile(
    "|".join(_CONFOUNDER_SIGNALS),
    re.IGNORECASE,
)


def _extract_heuristic(search_results: str) -> list[str]:
    """Extract confounder phrases from raw search text using regex signals."""
    found: list[str] = []
    for match in _CONFOUNDER_RE.finditer(search_results):
        # Take the first non-None group
        phrase = next((g for g in match.groups() if g), None)
        if phrase:
            cleaned = phrase.strip().rstrip(".,;")
            if 4 <= len(cleaned) <= 60:
                found.append(cleaned)

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for item in found:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique[:5]

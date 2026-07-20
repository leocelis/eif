"""Hard-to-vary check for falsification conditions (Deutsch criterion, §4.2b).

A good falsification condition must be hard-to-vary: every detail is
load-bearing. Changing the threshold, procedure, or observation produces
a visibly different test for a different hypothesis. Easy-to-vary conditions
can be quietly weakened when inconvenient evidence arrives - defeating FALSIFY.

Three checks applied independently:

  THRESHOLD - must contain a specific number or quantified bound.
    Qualitative language without a numeric anchor ("high", "significant",
    "poor", "excessive") makes the threshold retroactively reinterpretable.

  PROCEDURE - must name a specific tool, data source, API, query, or method.
    Generic verbs alone ("check if", "verify that", "see if", "make sure")
    give no stable observation specification and can be satisfied trivially.

  CONDITION - must not contain adjustable hedge language that could accommodate
    the opposite outcome ("might be lower", "could indicate", "may suggest").

All three checks are independent. Any one failure sets is_vague=True and
populates reasons[] with specific, actionable feedback.

Distinct from trivial_check.py (which catches vacuously satisfiable conditions
such as "always"/"never"). Hard-to-vary catches conditions that are non-trivial
in surface form but still too vague to be reliably falsifying.

Research:
  Deutsch, D. (2011). The Beginning of Infinity. Ch. 1 - hard-to-vary explanations.
  Operationalized in EIF Architecture framework §4.2b and §5.4 Adversarial Gaming.
"""

from __future__ import annotations

import re

# ── THRESHOLD check: qualitative words that lack numeric grounding ────────────

_QUALITATIVE_WORDS: frozenset[str] = frozenset({
    "high", "low", "significant", "excessive", "adequate", "sufficient",
    "poor", "good", "reasonable", "appropriate", "acceptable", "notable",
    "considerable", "substantial", "negligible", "minimal", "major",
    "minor", "large", "small", "many", "few", "some", "most",
    "elevated", "reduced", "normal", "abnormal", "typical", "atypical",
    "increased", "decreased", "strong", "weak", "fast", "slow",
    "better", "worse", "higher", "lower",
})

# Numeric anchor: a digit sequence (optionally with unit), or explicit zero/one...
_NUMERIC_ANCHOR = re.compile(
    r"\b\d+(\.\d+)?\s*"
    r"(%|ms|s\b|kb|mb|gb|tb|rpm|rps|day|week|month|hour|hr|min|minute|"
    r"k\b|m\b|b\b|x\b|ns\b|μs\b|us\b)?"
    r"|\b(zero|one|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.IGNORECASE,
)

# ── PROCEDURE check: vague action verbs without a named method ────────────────

_VAGUE_PROCEDURE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\bcheck\s+(if|whether|that|it|the)\b", re.IGNORECASE),
    re.compile(r"\bverify\s+(that|if|whether|it|the)\b", re.IGNORECASE),
    re.compile(r"\bconfirm\s+(if|whether|that|it|the)\b", re.IGNORECASE),
    re.compile(r"\bsee\s+if\b", re.IGNORECASE),
    re.compile(r"\bmake\s+sure\b", re.IGNORECASE),
    re.compile(r"\blook\s+at\b", re.IGNORECASE),
    re.compile(r"\blook\s+for\b", re.IGNORECASE),
    re.compile(r"\bensure\b", re.IGNORECASE),
    re.compile(r"\binspect\b", re.IGNORECASE),
    re.compile(r"\breview\b", re.IGNORECASE),
)

# Specific method indicators - presence of ANY of these neutralises vague verbs
_SPECIFIC_METHOD = re.compile(
    r"\b(api|sql|query|curl|http|https|rest|grpc|endpoint|rpc|"
    r"test|pytest|unittest|benchmark|metric|log|trace|monitor|"
    r"database|table|column|index|field|schema|"
    r"igdb|steam|jira|github|slack|datadog|bigquery|"
    r"function|method|script|command|tool|cli|shell)\b",
    re.IGNORECASE,
)

# ── CONDITION check: adjustable hedge language ────────────────────────────────

_ADJUSTABLE_PHRASES: tuple[str, ...] = (
    "might be",
    "could indicate",
    "could suggest",
    "may suggest",
    "may indicate",
    "might indicate",
    "possibly",
    "perhaps",
    "if applicable",
    "when possible",
    "as appropriate",
    "depending on",
    "under certain conditions",
    "in some cases",
    "generally",
    "typically",
    "usually",
)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def check_hard_to_vary(
    condition: str,
    threshold: str,
    test_procedure: str,
) -> tuple[bool, list[str]]:
    """Apply the Deutsch hard-to-vary criterion to a falsification condition.

    Returns:
        (is_vague, reasons) where is_vague=True means at least one dimension
        failed and the condition should be revised before relying on it.

    Each reason in reasons[] identifies the failing dimension (THRESHOLD /
    PROCEDURE / CONDITION) and provides specific revision guidance.
    """
    reasons: list[str] = []

    # ── Check 1: THRESHOLD ──────────────────────────────────────────────────
    threshold_stripped = threshold.strip()
    if threshold_stripped:
        has_number = bool(_NUMERIC_ANCHOR.search(threshold_stripped))
        threshold_words = set(threshold_stripped.lower().split())
        qualitative_matches = threshold_words & _QUALITATIVE_WORDS

        if qualitative_matches and not has_number:
            reasons.append(
                f"THRESHOLD is qualitative without a numeric anchor "
                f"({sorted(qualitative_matches)!r} found in {threshold_stripped!r}). "
                "Add a specific number - e.g., '< 100', '> 500 ms', '< 5%'."
            )

    # ── Check 2: PROCEDURE ──────────────────────────────────────────────────
    if test_procedure.strip():
        has_vague_verb = any(
            p.search(test_procedure) for p in _VAGUE_PROCEDURE_PATTERNS
        )
        has_specific_method = bool(_SPECIFIC_METHOD.search(test_procedure))

        if has_vague_verb and not has_specific_method:
            reasons.append(
                f"PROCEDURE uses a vague action verb without naming a specific "
                f"tool, data source, or method ({test_procedure[:80]!r}). "
                "Name the exact API, query, CLI command, or measurement that "
                "produces the observation - e.g., 'Query IGDB /games endpoint, "
                "field: hypes' or 'Run pytest suite, check exit code'."
            )

    # ── Check 3: CONDITION ──────────────────────────────────────────────────
    condition_lower = condition.lower()
    found_adjustable = [
        phrase for phrase in _ADJUSTABLE_PHRASES
        if phrase in condition_lower
    ]
    if found_adjustable:
        reasons.append(
            f"CONDITION contains adjustable language {found_adjustable!r} that "
            "allows retroactive reinterpretation to accommodate either outcome. "
            "State the exact observation that falsifies: "
            "'if X < Y, the claim is wrong' not 'X might indicate Y'."
        )

    return len(reasons) > 0, reasons

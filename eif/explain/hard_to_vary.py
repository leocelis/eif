"""Hard-to-vary check for explanation artifacts.

Implements Deutsch's criterion: every detail in an explanation must play
a functional role. A detail is functional iff altering it changes the prediction.

Algorithm from tech spec §4.2.

v4.1 addition: check_domain_specificity - domain-specificity anchor gate.
When system context is provided, every detail must reference at least one
high-specificity token from that context. Closes the S14 finding: GPT-4.1-mini's
deep parametric knowledge can produce syntactically specific-sounding details
that are still semantically domain-agnostic. Anchor-presence is a deterministic
proxy for system-specificity without requiring an LLM call.
"""

from __future__ import annotations

import re

from eif.schemas import ExplanationDetail, HardToVaryVerdict

GENERIC_PHRASES = {
    "changes the explanation",
    "affects the result",
    "makes it different",
    "would change things",
    "is important",
    "matters",
}

# Technology terms that are too widespread to serve as discriminative anchors
# even when they appear in a system context. Mentioning "Docker" doesn't make
# a detail system-specific - "Docker with XGBoost and FDA SaMD" does (other tokens fire).
_TECH_GENERICS = frozenset({
    "docker", "kubernetes", "python", "linux", "windows", "macos",
    "github", "gitlab", "jenkins", "grafana", "prometheus", "kibana",
    "tensorflow", "pytorch", "jupyter", "numpy", "pandas",
    "aws", "gcp", "azure", "json", "yaml", "http", "https",
    "rest", "api", "sql", "nosql", "oauth", "jwt", "html", "css",
    "server", "client", "backend", "frontend", "database", "storage",
})

_DIGIT_RE = re.compile(r"\d")
_ALLCAPS_RE = re.compile(r"^[A-Z]{3,}$")
_PUNCT_STRIP_RE = re.compile(r"^[\W_]+|[\W_]+$")


def _is_paraphrase(impact: str, detail: str) -> bool:
    """Return True if impact shares > 70% Jaccard overlap with detail text."""
    impact_tokens = set(impact.lower().split())
    detail_tokens = set(detail.lower().split())
    if not detail_tokens:
        return False
    overlap = len(impact_tokens & detail_tokens) / len(impact_tokens | detail_tokens)
    return overlap > 0.70


def extract_anchor_tokens(system_context: str) -> frozenset[str]:
    """Extract high-specificity anchor tokens from a system context string.

    An anchor is a token that is:
    - A number, threshold, rate, or version (contains a digit): "0.44", "180ms", "847K", "2TB"
    - An ALL-CAPS acronym of 3+ characters: "HIPAA", "FDA", "SOX", "PHI", "EKS", "SaMD"... no - 
      actually "SaMD" is mixed, so ALL-CAPS check: "HIPAA", "FDA", "SOX", "PHI", "EKS", "SLA"
    - A mixed-case proper noun of 7+ characters that is NOT a generic tech term:
      "PulseAPI", "FinCorp", "XGBoost", "Airflow", "Iceberg", "ReadmitPredict"

    Returns lowercased tokens for case-insensitive matching in check_domain_specificity.
    """
    anchors: set[str] = set()
    for raw_token in system_context.split():
        token = _PUNCT_STRIP_RE.sub("", raw_token)
        if not token:
            continue
        lower = token.lower()
        if lower in _TECH_GENERICS:
            continue
        if (
            _DIGIT_RE.search(token)                          # contains a digit
            or _ALLCAPS_RE.match(token)                       # ALL-CAPS acronym 3+
            or (len(token) >= 7 and token[0].isupper())       # proper noun 7+ chars
        ):
            anchors.add(lower)
    return frozenset(anchors)


def check_domain_specificity(
    details: list[ExplanationDetail],
    system_context: str,
) -> HardToVaryVerdict:
    """Domain-specificity gate: EXPLAIN v4.1.

    Returns FAIL if any detail contains NONE of the high-specificity anchor tokens
    extracted from system_context. A detail that references no system-specific term
    is domain-agnostic - it could apply to any system in this domain - and therefore
    IS easy to vary (substituting a different domain keyword leaves it intact).

    Returns PASS when:
    - system_context is empty (no anchor context available - skip the test)
    - fewer than 3 anchor tokens are extractable (context too sparse to discriminate)
    - all details reference at least one anchor token

    This is deterministic and requires no LLM call.

    Research basis (S14 corpus finding):
    - GPT-4.1-mini produces syntactically specific impacts ("if removed, performance degrades")
      that are semantically domain-agnostic. check_hard_to_vary cannot detect this.
    - Anchor-presence is an effective proxy: if a detail references "HS256", "HIPAA", "0.44",
      or "847K", it is tied to the specific system. Generic "Use retries with exponential
      backoff" references none of these.
    """
    if not system_context or not details:
        return "PASS"

    anchors = extract_anchor_tokens(system_context)
    if len(anchors) < 3:
        # Insufficient discriminative context - skip the test
        return "PASS"

    for d in details:
        # Check both the detail text and its prediction impact - a detail is
        # system-specific if EITHER field references an anchor token. Checking only
        # detail_text is too strict: an agent often encodes system-specificity in the
        # impact ("increasing OOM risk") rather than repeating the context token in
        # the detail text itself.
        combined = (d.detail_text + " " + d.prediction_impact).lower()
        if not any(anchor in combined for anchor in anchors):
            return "FAIL"

    return "PASS"


def check_hard_to_vary(details: list[ExplanationDetail]) -> HardToVaryVerdict:
    """Check if an explanation is hard to vary (all details are load-bearing).

    PASS: all details have non-empty, non-generic prediction_impact
    FAIL: at least one detail has empty or generic prediction_impact
    SELF_ASSESSED: never returned here - set by MCP layer when engine unavailable

    For the full EXPLAIN v4.1 check (including domain specificity when context is
    available), call check_domain_specificity() after this function.
    """
    if not details:
        return "FAIL"

    for detail in details:
        impact = detail.prediction_impact.strip()

        if not impact:
            return "FAIL"

        if _is_paraphrase(impact, detail.detail_text):
            return "FAIL"

        if impact.lower() in GENERIC_PHRASES:
            return "FAIL"

        # Only apply the length-ratio guard when the detail itself is long enough
        # to make the ratio meaningful. A short detail like "jsonify()" (9 chars)
        # will naturally have a longer impact description - that is not padding.
        MIN_DETAIL_FOR_RATIO = 20
        if (
            len(detail.detail_text) >= MIN_DETAIL_FOR_RATIO
            and len(impact) > 3 * len(detail.detail_text)
        ):
            return "FAIL"

    return "PASS"

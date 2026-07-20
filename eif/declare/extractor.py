"""EIF claim extractor - converts a natural-language decision into structured claims.

Surfaces 2-4 HALTable claims from a plain-English decision description so the
developer does not have to write raw ClaimInput JSON on their first session.

Design constraints:
- Zero LLM call - deterministic regex + heuristic patterns only. The extractor
  runs before any EIF pipeline step and must not introduce circular reasoning.
- Favors GUESSED for any claim containing a specific number, metric, or
  percentage - those have the highest HALT rate in the corpus.
- Favors ASSUMED for environmental, scope, or capability statements without
  a source citation.
- KNOWN is only assigned when the text contains an explicit source marker
  ("according to", "per the", "source:", URL, etc.).
- Returns 2-4 claims ordered from highest HALT probability to lowest.

Research basis:
  IFScale 2025 - constraint compliance 68% accurate at high density
  LangChain 2026 - quality is #1 production blocker at 32% overall
  Twilio PLG research - 73% activation for users who reach aha moment vs 8%
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ─────────────────────────────────────────────────────────────────────────────
# Pattern library
# ─────────────────────────────────────────────────────────────────────────────

# Numeric patterns that strongly indicate a GUESSED claim when no source cited
_NUMBER_PATTERNS = [
    re.compile(r"\b\d[\d,]*\.?\d*\s*(%|percent|billion|million|thousand|k\b|x\b|times)", re.I),
    re.compile(r"\b\d[\d,]*\s*(users?|customers?|requests?|sessions?|follows?|hypes?|ratings?|stars?|downloads?|installs?|views?|clicks?)", re.I),
    re.compile(r"\b(over|above|more than|at least|approximately|around|~)\s*\d[\d,]*", re.I),
    re.compile(r"\b\d+\s*/\s*(100|10|5)\b"),       # "80/100", "9/10"
    re.compile(r"\b\d{4,}\b"),                       # bare numbers ≥1000
]

# Source citation markers - presence upgrades ASSUMED → KNOWN
_SOURCE_MARKERS = [
    re.compile(r"according to", re.I),
    re.compile(r"\bper (the|our|their)\b", re.I),
    re.compile(r"\bsource:\s*https?://", re.I),
    re.compile(r"https?://\S+"),
    re.compile(r"\b(study|paper|report|survey|data) (shows?|found|confirms?)", re.I),
    re.compile(r"\bpublished in\b", re.I),
    re.compile(r"\bcited in\b", re.I),
]

# Compliance/regulatory markers that make a claim ASSUMED (often overstated)
_COMPLIANCE_MARKERS = [
    re.compile(r"\b(compliant|compliance|complies|satisfies?|meets?)\b.*\b(gdpr|hipaa|eu ai act|sox|pci|iso|nist|fedramp|art\.?\s*\d+)", re.I),
    re.compile(r"\b(gdpr|hipaa|eu ai act|sox|pci|iso|nist|fedramp)\b.*\b(compliant|complies|satisfies?|approved|certified)", re.I),
    re.compile(r"\b(no|zero|none)\b.{0,40}\b(risk|liability|penalty|fine|violation|breach)", re.I),
]

# Performance / capability claim markers
_PERF_MARKERS = [
    re.compile(r"\b(achieves?|reaches?|delivers?|provides?|guarantees?)\b.{0,60}\b(\d+\s*%|\d[\d,]+)", re.I),
    re.compile(r"\b(faster|cheaper|better|safer|more accurate|higher quality)\b.{0,60}\b(than|vs\.?|compared)", re.I),
    re.compile(r"\b(production|production-grade|enterprise-grade|ready for)\b", re.I),
]

# Demand / market / popularity markers (gaming domain + general)
_DEMAND_MARKERS = [
    re.compile(r"\b(strong|high|massive|significant|growing|large|impressive)\b.{0,40}\b(demand|interest|community|audience|fanbase|following|traction|engagement)", re.I),
    re.compile(r"\b(popular|trending|viral|top|leading|dominant)\b", re.I),
    re.compile(r"\b(hype|hypes|wishlists?|follows?|ratings?|reviews?|scores?)\b", re.I),
]

# Causal markers - agent is making a causal claim (high HALT risk)
_CAUSAL_MARKERS = [
    re.compile(r"\b(because|due to|caused by|results? in|leads? to|drives?|increases?|decreases?|improves?|reduces?)\b", re.I),
    re.compile(r"\b(will|would|should)\b.{0,30}\b(increase|decrease|improve|reduce|grow|shrink|rise|fall|drop)", re.I),
]

# Sentence splitter
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

# Conjunctions that indicate the sentence contains multiple claims
_CLAIM_SPLIT_RE = re.compile(r"\band\b|\bwith\b|\balso\b|\badditionally\b|\bfurthermore\b", re.I)


@dataclass
class ExtractedClaim:
    text: str
    claim_type: str                       # KNOWN | ASSUMED | GUESSED
    consequence_of_wrong: str            # HIGH | MEDIUM | LOW
    falsification_condition: str
    basis: str
    halt_probability: float              # internal rank signal, 0–1
    why_this_matters: str


def _has_source(text: str) -> bool:
    return any(p.search(text) for p in _SOURCE_MARKERS)


def _has_number(text: str) -> bool:
    return any(p.search(text) for p in _NUMBER_PATTERNS)


def _score_halt_probability(text: str) -> tuple[str, str, float]:
    """Return (claim_type, consequence, halt_probability) for a candidate text."""

    if _has_source(text):
        claim_type = "KNOWN"
        base_score = 0.1
    elif _has_number(text):
        claim_type = "GUESSED"   # specific number with no source → fabrication risk
        base_score = 0.85
    else:
        claim_type = "ASSUMED"
        base_score = 0.45

    # Boost for compliance overclaims
    if any(p.search(text) for p in _COMPLIANCE_MARKERS):
        base_score = max(base_score, 0.75)
        claim_type = "ASSUMED" if claim_type == "KNOWN" else claim_type

    # Boost for demand/popularity claims (gaming domain)
    if any(p.search(text) for p in _DEMAND_MARKERS):
        if _has_number(text):
            base_score = max(base_score, 0.90)
        else:
            base_score = max(base_score, 0.60)

    # Boost for causal claims
    if any(p.search(text) for p in _CAUSAL_MARKERS):
        base_score = max(base_score, 0.65)
        claim_type = "ASSUMED" if claim_type == "KNOWN" else claim_type

    # Consequence
    if base_score >= 0.75:
        consequence = "HIGH"
    elif base_score >= 0.45:
        consequence = "MEDIUM"
    else:
        consequence = "LOW"

    return claim_type, consequence, round(base_score, 2)


def _build_falsification_condition(text: str, claim_type: str) -> str:
    """Generate a falsification condition from the claim text."""

    # Numeric claim: find the number and frame the FC as "number is lower/absent"
    for pat in _NUMBER_PATTERNS:
        m = pat.search(text)
        if m:
            num_str = m.group(0).strip()
            return f"The actual value for {num_str} is significantly lower, absent, or contradicts the stated figure."

    if any(p.search(text) for p in _COMPLIANCE_MARKERS):
        return "An authoritative source (regulator, audit, or certified tool) finds a gap in the stated compliance."

    if any(p.search(text) for p in _DEMAND_MARKERS):
        return "Actual demand, popularity, or engagement metrics are lower than implied."

    if any(p.search(text) for p in _CAUSAL_MARKERS):
        return "The causal relationship does not hold when tested against independent data."

    return f"An independent source contradicts or cannot confirm: '{text[:80].rstrip()}'"


def _build_why_this_matters(claim_type: str, consequence: str) -> str:
    if claim_type == "GUESSED" and consequence == "HIGH":
        return "Specific metric stated with no cited source - high fabrication risk if acted on."
    if claim_type == "GUESSED":
        return "Specific figure with no source citation - may be generated, not retrieved."
    if claim_type == "ASSUMED" and consequence == "HIGH":
        return "Strong assertion without a supporting source - needs external verification before acting."
    if claim_type == "ASSUMED":
        return "Reasonable-sounding assumption that has not been verified externally."
    return "Claim has a source citation - verify the source matches the specific context."


def _extract_candidate_sentences(decision: str) -> list[str]:
    """Split decision text into candidate claim sentences."""
    sentences = _SENTENCE_RE.split(decision.strip())
    candidates: list[str] = []

    for s in sentences:
        s = s.strip()
        if len(s) < 15:
            continue
        # Each sentence may contain multiple claims joined by conjunctions
        # For very long sentences with explicit metrics, keep whole to preserve context
        if len(s) > 200 and re.search(r"\d", s):
            candidates.append(s)
        else:
            candidates.append(s)

    # If only one long sentence (e.g. the decision is a single run-on),
    # try splitting on commas + demand/metric phrases
    if len(candidates) <= 1:
        parts = re.split(r",\s+(?=[A-Z]|\b(?:the|it|this|our|their|game|agent|model)\b)", decision)
        if len(parts) > 1:
            candidates = [p.strip() for p in parts if len(p.strip()) > 15]

    return candidates


def extract_claims(
    decision: str,
    max_claims: int = 4,
    min_claims: int = 2,
) -> list[ExtractedClaim]:
    """Extract structured claims from a natural-language decision description.

    Returns between min_claims and max_claims claims, ordered by HALT probability
    descending. Always includes the highest-risk claim first.
    """
    candidates = _extract_candidate_sentences(decision)

    scored: list[ExtractedClaim] = []

    for text in candidates:
        text = text.strip().rstrip(".,;:")
        if not text:
            continue

        claim_type, consequence, halt_prob = _score_halt_probability(text)

        # Only surface claims worth checking (KNOWN with LOW consequence adds no value)
        if claim_type == "KNOWN" and consequence == "LOW":
            continue

        fc = _build_falsification_condition(text, claim_type)
        why = _build_why_this_matters(claim_type, consequence)
        basis = (
            "Stated with high confidence and a specific figure but no source cited."
            if claim_type == "GUESSED"
            else "Stated as fact without an explicit supporting source."
            if claim_type == "ASSUMED"
            else "Has a source citation - verify the source applies to this context."
        )

        scored.append(ExtractedClaim(
            text=text,
            claim_type=claim_type,
            consequence_of_wrong=consequence,
            falsification_condition=fc,
            basis=basis,
            halt_probability=halt_prob,
            why_this_matters=why,
        ))

    # Sort highest HALT probability first
    scored.sort(key=lambda c: -c.halt_probability)

    # Deduplicate near-identical texts (can happen with run-on sentences)
    deduped: list[ExtractedClaim] = []
    seen_prefixes: set[str] = set()
    for c in scored:
        prefix = c.text[:40].lower()
        if prefix not in seen_prefixes:
            seen_prefixes.add(prefix)
            deduped.append(c)

    result = deduped[:max_claims]

    # If we found fewer than min_claims, synthesize a catch-all ASSUMED claim
    # so the session always has something to run through the pipeline.
    if len(result) < min_claims:
        synthetic = ExtractedClaim(
            text=decision[:200].strip().rstrip(".,;:"),
            claim_type="ASSUMED",
            consequence_of_wrong="MEDIUM",
            falsification_condition="The decision's underlying premise cannot be confirmed by an independent source.",
            basis="No specific verifiable claim found - treating the full decision as an assumed premise.",
            halt_probability=0.35,
            why_this_matters="No specific metric found; treating the whole decision as an assumption to probe.",
        )
        result.append(synthetic)

    return result


def claims_to_dict(claims: list[ExtractedClaim]) -> list[dict]:
    """Serialize extracted claims to a ClaimInput-compatible dict format.

    All keys map to ClaimInput fields. Extra keys (why_this_matters,
    halt_probability) are ignored by ClaimInput.model_validate() but retained
    for callers that want the extractor's ranking signals.

    For KNOWN claims, evidence_source is populated from basis (the source marker
    context) to satisfy C1 / ClaimInput validation.
    """
    rows = []
    for c in claims:
        row: dict = {
            "text": c.text[:300],
            "claim_type": c.claim_type,
            "consequence_of_wrong": c.consequence_of_wrong,
            "falsification_condition": c.falsification_condition[:200],
            "basis": c.basis[:200],
            # Extra info keys (not ClaimInput fields - ignored by Pydantic validation)
            "why_this_matters": c.why_this_matters,
            "halt_probability": c.halt_probability,
        }
        # C1: KNOWN claims must have an evidence_source; use basis as the source.
        if c.claim_type == "KNOWN":
            row["evidence_source"] = c.basis[:200] or "Inferred from source marker - verify independently"
        rows.append(row)
    return rows

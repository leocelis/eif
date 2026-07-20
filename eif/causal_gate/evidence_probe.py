"""CAUSAL_GATE v4 - Causal Evidence Probe (CEP).

Fires when a claim is classified at INTERVENTION or COUNTERFACTUAL level
AND consequence_of_wrong == "HIGH". Searches for independent causal evidence
(RCTs, meta-analyses, natural experiments) via P3 DDGS and returns a
structured CausalEvidenceResult.

Design: We do NOT build DAGs or run do-calculus. We search for whether the
causal question has already been answered by the scientific community.
See: eif/eif/causal_gate/eif_causal_gate_v4_intent.yaml (CG1–CG7)

Research basis:
  ERM (arXiv:2602.11675) - Rung Collapse: LLMs confuse P(Y|X) with P(Y|do(X))
  ReCITE (arXiv:2505.18931) - Best LLM F1=0.535 on causal extraction
  Ariadne (arXiv:2601.02314) - Reasoning traces unfaithful to causal logic
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import datetime

from eif.causal_gate.confound import discover_confounders
from eif.causal_gate.verdict import posterior_delta, provenance_flag_for
from eif.schemas import CausalEvidenceResult, CausalEvidenceVerdict, CausalLevel

_log = logging.getLogger(__name__)

# Trigger conditions for CEP (CG1)
CEP_TRIGGER_LEVELS: frozenset[str] = frozenset({"INTERVENTION", "COUNTERFACTUAL"})
CEP_TRIGGER_CONSEQUENCE: str = "HIGH"

# Causal evidence search keyword suffix (CG2)
_CAUSAL_SEARCH_SUFFIX = "RCT OR meta-analysis OR randomized OR natural experiment OR causal"


# ─────────────────────────────────────────────────────────────────────────────
# Public trigger guard
# ─────────────────────────────────────────────────────────────────────────────

def should_probe(causal_level: CausalLevel, consequence: str) -> bool:
    """Return True if the claim meets the CEP trigger conditions (CG1)."""
    return causal_level in CEP_TRIGGER_LEVELS and consequence == CEP_TRIGGER_CONSEQUENCE


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: extract (cause, effect, domain) from claim text
# ─────────────────────────────────────────────────────────────────────────────

_EXTRACT_PROMPT = """\
Given this causal claim: "{claim_text}"

Extract exactly three fields:
- cause: the variable proposed as the cause
- effect: the variable proposed as the effect
- domain: the field or sector (e.g. healthcare, engineering, finance, software)

Return only valid JSON with keys "cause", "effect", "domain". No commentary.
"""


def extract_causal_pair(
    claim_text: str,
    llm_fn: Callable[[str], str],
) -> tuple[str, str, str]:
    """Extract (cause, effect, domain) from a causal claim via a lightweight LLM call.

    Args:
        claim_text: raw claim text, e.g. "microservices reduce deployment failures"
        llm_fn: callable(prompt) -> response_text (injectable for testing)

    Returns:
        (cause, effect, domain) tuple. Falls back to heuristics if LLM fails.
    """
    prompt = _EXTRACT_PROMPT.format(claim_text=claim_text)
    try:
        raw = llm_fn(prompt)
        # Accept raw JSON or JSON wrapped in markdown fences
        json_text = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", raw, flags=re.DOTALL).strip()
        parsed = json.loads(json_text)
        cause = str(parsed.get("cause", "")).strip()
        effect = str(parsed.get("effect", "")).strip()
        domain = str(parsed.get("domain", "")).strip()
        if cause and effect:
            return cause, effect, domain or "general"
    except Exception:  # noqa: BLE001
        _log.debug("extract_causal_pair: LLM parse failed, falling back to heuristic")

    # Heuristic fallback: use the full claim as cause, "outcome" as effect
    return claim_text, "outcome", "general"


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: formulate search query (CG2)
# ─────────────────────────────────────────────────────────────────────────────

def formulate_search_query(cause: str, effect: str, domain: str) -> str:
    """Build a P3 search query targeting causal evidence for the (cause, effect) pair.

    The suffix ensures results are filtered toward RCTs and meta-analyses (CG2).
    """
    return f"{cause} {effect} {_CAUSAL_SEARCH_SUFFIX} {domain}".strip()


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: P3 search via DDGS native_search
# ─────────────────────────────────────────────────────────────────────────────

def _run_search(query: str, search_fn: Callable[[str], str] | None = None) -> str:
    """Execute the P3 DDGS search. Falls back gracefully to empty string on failure."""
    if search_fn is not None:
        return search_fn(query)

    # Default: use EIF native_search (DDGS, no API key)
    try:
        from eif.falsify.native_tools import native_search  # noqa: PLC0415
        return native_search(query, max_results=5)
    except Exception:  # noqa: BLE001
        _log.warning("CEP: native_search unavailable - returning empty results")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: classify search results into CausalEvidenceVerdict (CG3, CG7)
# ─────────────────────────────────────────────────────────────────────────────

_CLASSIFY_PROMPT = """\
You are an evidence classifier for a causal inference system.

Given these search results about whether "{cause}" causally affects "{effect}":

---
{search_results}
---

Classify the causal evidence into exactly one verdict:
- SUPPORTED: An RCT, meta-analysis, natural experiment, or Cochrane review was found
  that supports this causal direction
- CONTESTED: Evidence was found but shows a null effect, conflicting results, or
  disputes the claimed direction
- NO_EVIDENCE: No causal studies (RCTs, meta-analyses, natural experiments) were found
  for this specific relationship - observational associations alone do not qualify
- REVERSED: Evidence supports the opposite causal direction

Rules:
1. Only use SUPPORTED if actual causal study methodology is evident (RCT, natural
   experiment, IV, regression discontinuity, etc.) - not mere correlation
2. Citation must include study name/title and year if verdict is SUPPORTED or REVERSED
3. If the search results contain only observational data or no relevant studies,
   return NO_EVIDENCE

Return only valid JSON: {{"verdict": "...", "citation": "study title (year)" or null}}
No commentary outside the JSON.
"""


def classify_evidence(
    cause: str,
    effect: str,
    search_results: str,
    llm_fn: Callable[[str], str],
) -> tuple[CausalEvidenceVerdict, str | None]:
    """Classify P3 search results into a CausalEvidenceVerdict + citation (CG3, CG7).

    Args:
        cause: extracted cause variable
        effect: extracted effect variable
        search_results: concatenated P3 search output
        llm_fn: callable(prompt) -> response_text

    Returns:
        (verdict, citation) - citation is None when verdict is NO_EVIDENCE.
    """
    if not search_results.strip():
        return "NO_EVIDENCE", None

    prompt = _CLASSIFY_PROMPT.format(
        cause=cause,
        effect=effect,
        search_results=search_results[:3000],  # guard against token overflow
    )
    try:
        raw = llm_fn(prompt)
        json_text = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", raw, flags=re.DOTALL).strip()
        parsed = json.loads(json_text)
        raw_verdict = str(parsed.get("verdict", "NO_EVIDENCE")).upper()
        citation = parsed.get("citation") or None

        valid_verdicts: set[str] = {"SUPPORTED", "CONTESTED", "NO_EVIDENCE", "REVERSED"}
        if raw_verdict not in valid_verdicts:
            raw_verdict = "NO_EVIDENCE"

        # CG7: all non-neutral verdicts must carry a citation; CONTESTED without
        # a citation is also unreliable (neither side citable → no evidence).
        if raw_verdict in ("SUPPORTED", "REVERSED", "CONTESTED") and not citation:
            _log.warning("CEP: %s verdict has no citation - downgraded to NO_EVIDENCE", raw_verdict)
            raw_verdict = "NO_EVIDENCE"

        return raw_verdict, citation  # type: ignore[return-value]

    except Exception:  # noqa: BLE001
        _log.debug("CEP: classify_evidence LLM parse failed - returning NO_EVIDENCE")
        return "NO_EVIDENCE", None


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_causal_evidence_probe(
    claim_text: str,
    causal_level: CausalLevel,
    consequence: str,
    llm_fn: Callable[[str], str],
    search_fn: Callable[[str], str] | None = None,
) -> CausalEvidenceResult | None:
    """Run the Causal Evidence Probe (CEP) for a single claim.

    Returns None immediately if the claim does not meet trigger conditions (CG1).
    Returns a CausalEvidenceResult with verdict, citation, posterior_delta, and
    provenance_flag otherwise.

    Args:
        claim_text: raw claim text from DECLARE
        causal_level: ASSOCIATION / INTERVENTION / COUNTERFACTUAL (from CAUSAL_GATE v3)
        consequence: HIGH / MEDIUM / LOW (from Claim.consequence_of_wrong)
        llm_fn: callable(prompt) -> str - lightweight LLM (e.g. gpt-4.1-mini)
        search_fn: optional override for P3 search (default: DDGS native_search)

    Raises:
        Nothing - all failures are caught and result in NO_EVIDENCE verdict.
    """
    if not should_probe(causal_level, consequence):
        return None

    _log.info("CEP: probing claim=%r level=%s consequence=%s", claim_text, causal_level, consequence)

    cause, effect, domain = extract_causal_pair(claim_text, llm_fn)
    query = formulate_search_query(cause, effect, domain)
    search_results = _run_search(query, search_fn)
    verdict, citation = classify_evidence(cause, effect, search_results, llm_fn)

    # IRIS step: discover confounders not already named in the claim
    novel_confounders = discover_confounders(
        cause=cause,
        effect=effect,
        domain=domain,
        hypothesis=claim_text,
        search_fn=search_fn,
        llm_fn=llm_fn,
    )

    delta = posterior_delta(verdict)
    flag = provenance_flag_for(verdict, consequence)

    result = CausalEvidenceResult(
        claim_text=claim_text,
        cause=cause,
        effect=effect,
        domain=domain,
        causal_level=causal_level,
        search_query=query,
        verdict=verdict,
        citation=citation,
        evidence_summary=search_results[:500] if search_results else "",
        evidence_source="P3_WEB_SEARCH",
        posterior_delta=delta,
        provenance_flag=flag,
        discovered_confounders=novel_confounders,
        probed_at=datetime.utcnow(),
    )

    _log.info(
        "CEP result: verdict=%s citation=%r delta=%+.2f flag=%s",
        verdict, citation, delta, flag,
    )
    return result

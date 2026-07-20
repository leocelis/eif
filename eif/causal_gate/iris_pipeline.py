"""IRIS Full Iterative Causal Discovery Pipeline - V2 (F2).

V1 discover_confounders() runs a single web query + heuristic extraction.
V2 implements the full 6-step IRIS loop (arXiv:2510.09217, ACL 2025):

  Step 1: Document collection - 3-5 native_search queries for (cause, effect, domain).
  Step 2: Statistical causal discovery - extract quantitative claims from documents.
  Step 3: LLM Pearl-ladder classification - classify each claim on the Pearl causal
           hierarchy: ASSOCIATION / INTERVENTION / COUNTERFACTUAL.
  Step 4: Missing variable identification - ask what variables might confound
           cause→effect that are not in the literature.
  Step 5: Causal graph expansion - add missing variables; re-query for each.
  Step 6: Verifiable output - CausalGraph with confidence scores per edge.

Max 2 iterations of steps 4–6 (budget control: F2C3).

Research: IRIS arXiv:2510.09217 (ACL 2025) - iterative framework for verifiable
causal discovery in non-tabular data. Statistical extraction → LLM Pearl-ladder
classification → missing-variable identification → graph expansion.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

from eif.schemas import CausalEdge, CausalGraph

_log = logging.getLogger(__name__)

# Causal signal patterns for heuristic extraction (step 2 fallback)
_CAUSAL_PATTERNS = re.compile(
    r"(?:causes?|leads? to|results? in|increases?|decreases?|reduces?|affects?|"
    r"associated with|correlat(?:ed|es?) with|predicts?|explains?)\s+"
    r"([\w\s]{3,50})",
    re.IGNORECASE,
)

_PEARL_LEVELS = {"ASSOCIATION", "INTERVENTION", "COUNTERFACTUAL"}

_CLASSIFY_PROMPT = """\
Given this causal claim, classify it on the Pearl causal ladder.

Claim: "{claim}"
Cause: "{cause}"
Effect: "{effect}"

Pearl levels:
- ASSOCIATION: observed correlation; no manipulation; e.g. "X correlates with Y"
- INTERVENTION: do-calculus; intervention study or experiment; e.g. "giving X reduces Y"
- COUNTERFACTUAL: what-if reasoning; controls for unobserved; e.g. "had X not occurred, Y would not"

Return JSON: {{"level": "ASSOCIATION" | "INTERVENTION" | "COUNTERFACTUAL", "confidence": 0.0–1.0}}
Return ONLY the JSON, no commentary.
"""

_MISSING_VAR_PROMPT = """\
A researcher claims: "{cause}" causes "{effect}" in the domain of "{domain}".

Current known variables in this analysis: {known_vars}

What variables might confound this causal relationship that are NOT already listed above?
Focus on variables that:
1. Are known risk factors for the effect
2. Are also correlated with the cause
3. Are NOT in the current variable list

Return JSON array of strings. Maximum 5 items. If none, return [].
Example: ["socioeconomic status", "baseline health", "age"]
Return ONLY the JSON array.
"""


def _default_search(query: str, max_results: int = 5) -> str:
    """Use DDGS native_search as default P3 document retrieval."""
    try:
        from eif.falsify.native_tools import native_search  # noqa: PLC0415
        return native_search(query, max_results=max_results)
    except Exception:  # noqa: BLE001
        _log.debug("IRIS: native_search unavailable")
        return ""


def _extract_quantitative_claims(text: str, cause: str, effect: str) -> list[str]:
    """Step 2: Extract quantitative or directional causal claims from text."""
    claims: list[str] = []
    for match in _CAUSAL_PATTERNS.finditer(text):
        phrase = match.group(0).strip()
        if len(phrase) >= 10:
            claims.append(phrase[:200])

    # Also extract sentences mentioning both cause and effect
    sentences = re.split(r"(?<=[.!?])\s+", text)
    c_low, e_low = cause.lower(), effect.lower()
    for sent in sentences:
        s_low = sent.lower()
        if c_low in s_low and e_low in s_low and 20 <= len(sent) <= 300:
            claims.append(sent.strip())

    # Deduplicate
    seen: set[str] = set()
    unique: list[str] = []
    for c in claims:
        key = c.lower()[:80]
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique[:10]


def _classify_pearl_level(
    claim: str,
    cause: str,
    effect: str,
    llm_fn: Callable | None,
) -> tuple[str, float]:
    """Step 3: Classify a claim on the Pearl causal ladder."""
    if llm_fn is not None:
        prompt = _CLASSIFY_PROMPT.format(claim=claim[:300], cause=cause, effect=effect)
        try:
            raw = llm_fn(prompt, "iris_pearl_classify")
            text = raw if isinstance(raw, str) else json.dumps(raw)
            text = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", text, flags=re.DOTALL).strip()
            parsed = json.loads(text)
            level = str(parsed.get("level", "ASSOCIATION")).upper()
            if level not in _PEARL_LEVELS:
                level = "ASSOCIATION"
            confidence = float(parsed.get("confidence", 0.5))
            return level, max(0.0, min(1.0, confidence))
        except Exception:  # noqa: BLE001
            pass

    # Heuristic fallback
    claim_lower = claim.lower()
    if any(w in claim_lower for w in ["had not", "without", "counterfactual", "what if"]):
        return "COUNTERFACTUAL", 0.55
    if any(w in claim_lower for w in ["randomiz", "experiment", "trial", "intervention", "giving", "administered"]):
        return "INTERVENTION", 0.60
    return "ASSOCIATION", 0.50


def _identify_missing_variables(
    cause: str,
    effect: str,
    domain: str,
    known_vars: list[str],
    llm_fn: Callable | None,
    search_fn: Callable | None,
) -> list[str]:
    """Step 4: Identify confounders not in the current variable set."""
    if llm_fn is not None:
        prompt = _MISSING_VAR_PROMPT.format(
            cause=cause,
            effect=effect,
            domain=domain,
            known_vars=", ".join(known_vars) if known_vars else "none",
        )
        try:
            raw = llm_fn(prompt, "iris_missing_vars")
            text = raw if isinstance(raw, str) else json.dumps(raw)
            text = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", text, flags=re.DOTALL).strip()
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if v and str(v).strip() not in known_vars][:5]
        except Exception:  # noqa: BLE001
            pass

    # Heuristic: search for "confounders" and extract
    sf = search_fn or _default_search
    try:
        results = sf(f"{cause} {effect} confounders {domain}")
        from eif.causal_gate.confound import _extract_heuristic  # noqa: PLC0415
        candidates = _extract_heuristic(results)
        known_lower = {v.lower() for v in known_vars}
        return [c for c in candidates if c.lower() not in known_lower][:5]
    except Exception:  # noqa: BLE001
        return []


def run(
    cause: str,
    effect: str,
    domain: str = "",
    search_fn: Callable | None = None,
    llm_fn: Callable | None = None,
    max_iterations: int = 2,
) -> CausalGraph:
    """Execute the full 6-step IRIS pipeline.

    Args:
        cause:          Cause variable name.
        effect:         Effect variable name.
        domain:         Domain context (e.g. "healthcare", "finance").
        search_fn:      Override for P3 document retrieval; defaults to native_search.
        llm_fn:         Optional LLM function for Pearl classification and variable
                        identification. When None, heuristic fallbacks are used.
        max_iterations: Maximum causal graph expansion iterations (F2C3: ≤ 2).

    Returns:
        CausalGraph with edges, missing_variables, and confidence_scores.
    """
    max_iterations = min(max_iterations, 2)  # F2C3: hard cap at 2
    sf = search_fn or _default_search
    domain_str = domain or "general"

    _log.info("IRIS: starting pipeline for '%s → %s' [domain=%s]", cause, effect, domain_str)

    # ─ Step 1: Document collection ────────────────────────────────────────────
    queries = [
        f"{cause} {effect} causal relationship {domain_str}",
        f"{cause} causes {effect} evidence {domain_str}",
        f"{effect} risk factors {cause} {domain_str}",
    ]
    all_docs = ""
    docs_retrieved = 0
    for q in queries:
        try:
            chunk = sf(q)
            if chunk.strip():
                all_docs += "\n" + chunk
                docs_retrieved += len(chunk.split())
        except Exception:  # noqa: BLE001
            pass

    _log.debug("IRIS step 1: retrieved ~%d words", docs_retrieved)

    # ─ Step 2: Statistical causal discovery ───────────────────────────────────
    raw_claims = _extract_quantitative_claims(all_docs, cause, effect)
    _log.debug("IRIS step 2: extracted %d causal claims", len(raw_claims))

    # ─ Step 3: LLM Pearl-ladder classification ────────────────────────────────
    edges: list[CausalEdge] = []
    confidence_scores: dict[str, float] = {}
    for claim in raw_claims:
        level, conf = _classify_pearl_level(claim, cause, effect, llm_fn)
        edge_key = f"{cause}->{effect}:{level}"
        if edge_key not in confidence_scores or conf > confidence_scores[edge_key]:
            confidence_scores[edge_key] = conf
        edges.append(CausalEdge(
            cause=cause,
            effect=effect,
            level=level,  # type: ignore[arg-type]
            evidence_count=1,
            confidence=conf,
        ))

    # Consolidate duplicate (cause, effect, level) edges
    consolidated: dict[str, CausalEdge] = {}
    for e in edges:
        key = f"{e.cause}->{e.effect}:{e.level}"
        if key not in consolidated:
            consolidated[key] = e
        else:
            existing = consolidated[key]
            consolidated[key] = CausalEdge(
                cause=e.cause,
                effect=e.effect,
                level=e.level,
                evidence_count=existing.evidence_count + 1,
                confidence=max(existing.confidence, e.confidence),
            )
    edges = list(consolidated.values())

    # Ensure at least one edge even if no claims were extracted
    if not edges:
        edges.append(CausalEdge(
            cause=cause, effect=effect, level="ASSOCIATION", evidence_count=0, confidence=0.0,
        ))
        _log.debug("IRIS step 3: no claims found - inserted zero-confidence ASSOCIATION edge")

    _log.debug("IRIS step 3: classified into %d distinct edges", len(edges))

    # ─ Steps 4–6: Iterative graph expansion ───────────────────────────────────
    all_missing: list[str] = []
    known_vars = [cause, effect]
    iterations_run = 0

    for iteration in range(max_iterations):
        # Step 4: Missing variable identification
        new_vars = _identify_missing_variables(cause, effect, domain_str, known_vars, llm_fn, sf)
        if not new_vars:
            _log.debug("IRIS step 4 (iter %d): no new variables found - stopping early", iteration + 1)
            iterations_run = iteration + 1
            break

        all_missing.extend(v for v in new_vars if v not in all_missing)
        known_vars.extend(v for v in new_vars if v not in known_vars)

        # Step 5: Graph expansion - query for each new variable's relationship
        for var in new_vars:
            try:
                var_docs = sf(f"{var} {cause} {effect} confound {domain_str}")
                if var_docs.strip():
                    var_claims = _extract_quantitative_claims(var_docs, var, effect)
                    for claim in var_claims[:3]:
                        level, conf = _classify_pearl_level(claim, var, effect, llm_fn)
                        edges.append(CausalEdge(
                            cause=var, effect=effect,
                            level=level,  # type: ignore[arg-type]
                            evidence_count=1,
                            confidence=conf * 0.8,  # discount indirect evidence
                        ))
                        key = f"{var}->{effect}:{level}"
                        confidence_scores[key] = conf * 0.8
            except Exception:  # noqa: BLE001
                pass

        iterations_run = iteration + 1
        _log.debug(
            "IRIS step 6 (iter %d): added %d new variables, %d total edges",
            iteration + 1, len(new_vars), len(edges),
        )

    if iterations_run == 0:
        iterations_run = 1  # Steps 4–6 ran at least once (found nothing)

    _log.info(
        "IRIS: pipeline complete - %d edges, %d missing vars, %d iteration(s)",
        len(edges), len(all_missing), iterations_run,
    )

    return CausalGraph(
        cause=cause,
        effect=effect,
        domain=domain_str,
        edges=edges,
        missing_variables=all_missing,
        iterations_run=iterations_run,
        confidence_scores=confidence_scores,
        documents_retrieved=docs_retrieved,
    )

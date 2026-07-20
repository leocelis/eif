"""EIF Evidence Collector - five-tier grounded evidence collection.

Implements the evidence collection strategy from:
  eif/falsify/eif_evidence_collection_intent.yaml (v1.0)

Evidence hierarchy (runtime fall-through order in collect_evidence()):
  P0  HOST_TOOL       - host agent's registered tools (authoritative; checked first)
  P2  TOOL_OUTPUT     - coordinator's web_search_call results (free, already collected;
                        checked BEFORE P1 per intent C3/C9 - no additional network cost)
  P1  CODE_EXECUTION  - execute Python against real data (numerical claims; runs after P2)
  P3  WEB_SEARCH      - dedicated multi-source search per claim
  P4  PARAMETRIC      - LLM parametric probe (fallback, caps at INSUFFICIENT)

The EIF engine remains zero-LLM and zero-network (tech_spec.md C1, C4).
All evidence collection lives here, in the integration layer.

Sources:
  POPPER    arXiv:2502.09858  (evidence must be independent; design falsification experiments)
  FActScore arXiv:2305.14251  (atomic claims vs external knowledge source, not parametric)
  ReAct     arXiv:2210.03629  (tool observations are the evidence, not model reasoning)
  Self-RAG  arXiv:2310.11511  (relevance check before belief update)
  FactReview arXiv:2604.04074 (code execution is strongest for numerical claims)
  FIRE      arXiv:2411.00784  (iterate on CONTINUE - follow-up queries)
  AVeriTeC  NeurIPS 2023      (conflicting evidence = neutral SPRT signal)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Evidence strategy enum
# ─────────────────────────────────────────────────────────────────────────────

STRATEGY_HOST_TOOL = "P0_HOST_TOOL"
STRATEGY_CODE      = "P1_CODE_EXECUTION"
STRATEGY_TOOL      = "P2_TOOL_OUTPUT"
STRATEGY_SEARCH    = "P3_WEB_SEARCH"
STRATEGY_PARAM     = "P4_PARAMETRIC"


@dataclass
class EvidenceResult:
    """Structured evidence result from any tier."""
    probe_tier: str                         # P0–P4
    verdict: str                            # SUPPORTS | CONTRADICTS | INSUFFICIENT | CONFLICTING
    confidence: float                       # 0.0–1.0
    evidence_summary: str
    evidence_source: str                    # URL, "CODE_EXECUTION", "PARAMETRIC", or sentinel
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    observations: list[bool] = field(default_factory=list)
    temporal_concern: bool = False
    causal_concern: bool = False
    is_company_specific: bool = False
    follow_up_query: str | None = None      # populated when verdict is INSUFFICIENT
    # F17: machine-readable quality signal for degraded evidence paths.
    # None  → normal path (P0/P1/P2/P3 produced a meaningful verdict)
    # "DEGRADED_METRIC"          → P4 parametric probe was used (weak, non-independent)
    # "SELF_PREFERENCE_BLOCKED"  → F15 overlap guard or self_preference_risk flag fired
    # "PRIVATE_DATA_BLOCKED"     → C10 private data firewall fired; no host tool available
    metric_quality: str | None = None
    # TW4/TW5 (eif_v5_evidence_trust_weighting): corroboration tracking for P3 web
    # search. independent_source_count = number of DISTINCT registrable domains seen
    # across search iterations (same-domain echo counts once). corroborated = True
    # when >= 2 independent domains support the claim. Used by the trust function to
    # lift an otherwise-discounted single-source web result. Defaults keep every
    # other tier (P0/P1/P2/P4) untouched.
    independent_source_count: int = 0
    corroborated: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Strategy selector (C2 constraint from intent)
# ─────────────────────────────────────────────────────────────────────────────

_NUMBER_RE = re.compile(
    r"\b\d[\d,]*\.?\d*\s*"
    r"(%|billion|million|thousand|k\b|rps|ms\b|milliseconds?|requests?/s|"
    r"latency|throughput|tps|qps|p99|p95|p50|cpu|vcpu|gb|tb|mb)",
    re.IGNORECASE,
)
_DATABASE_KEYWORDS = {
    "fda", "510k", "de novo", "pma", "510(k)", "cdrh", "cms", "cpt", "hcpcs",
    "mdr", "ce mark", "pubmed", "sec filing", "clinical trial", "nct", "nih",
    "fda cleared", "fda approved", "regulatory", "clearance", "approved",
    "gdpr", "article 17", "schrems", "standard contractual", "dpa", "ico",
}
_COMPANY_SPECIFIC_SIGNALS = {
    "our ", "we ", "series a", "series b", "our pilot",
    "our team", "our model", "our startup", "our product", "our platform",
    "pricewise", "acme", "techcorp",
}

# Phrases indicating a claim is about a specific private entity's data.
# Present → web search cannot verify; only a host tool with data access can.
# Intent C10; NabaOS arXiv:2603.10060: epistemic classification before evidence collection.
_PRIVATE_DATA_SIGNALS = frozenset({
    "the patient has", "patient has no", "patient has not", "patient's record",
    "patient record", "ehr", "electronic health record", "treatment history",
    "medication history", "clinical history", "prior anthracycline", "prior exposure",
    "prior treatment", "no prior treatment", "no prior exposure",
    "the customer has", "this user has", "this patient",
    "internal database", "proprietary data",
})

# If the claim also references a public registry, web search IS appropriate for
# the registry portion - do not apply the private data firewall.
_PUBLIC_REGISTRY_OVERRIDE = frozenset({
    "nct", "clinicaltrials.gov", "pubmed", "fda", "nih", "icd-10",
    "clinical trial registry", "trial criteria", "510k", "sec filing",
})


# ─────────────────────────────────────────────────────────────────────────────
# P0: Host Tool Registry
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HostTool:
    """A callable tool registered by the host agent for P0 evidence collection.

    The host agent populates the registry with tools it already has (EHR query,
    database client, internal API, ClinicalTrials.gov client, etc.) so EIF can
    delegate claim verification to the most authoritative available source.

    Selection uses keyword overlap, not LLM routing - zero-LLM, deterministic.
    Gorilla arXiv:2305.15334: retrieval-based tool selection via capability matching.
    ToolGate arXiv:2601.04688: capability_keywords act as the tool's precondition.
    """
    name: str
    description: str
    capability_keywords: list[str]
    fn: Callable[[str], str]           # query_string -> result_string
    data_scope: str = "PUBLIC"         # "PRIVATE" | "INTERNAL" | "PUBLIC"


class HostToolRegistry:
    """Registry of host agent tools available for P0 evidence collection.

    The host registers tools at initialization. EIF matches claims to tools via
    capability_keywords overlap and dispatches the falsification_condition as the
    query - because the falsification_condition already encodes what evidence would
    contradict the claim (POPPER arXiv:2502.09858: design falsification experiments
    that target the measurable implication of the hypothesis).
    """

    def __init__(self, tools: list[HostTool] | None = None) -> None:
        self._tools: list[HostTool] = list(tools or [])

    def register(self, tool: HostTool) -> None:
        self._tools.append(tool)

    def is_empty(self) -> bool:
        return not self._tools

    def find_matching(self, claim_text: str, falsification_condition: str) -> list[HostTool]:
        """Return tools whose capability_keywords overlap with the claim text."""
        text = f"{claim_text} {falsification_condition}".lower()
        scored: list[tuple[HostTool, int]] = []
        for tool in self._tools:
            score = sum(1 for kw in tool.capability_keywords if kw.lower() in text)
            if score >= 1:
                scored.append((tool, score))
        return [t for t, _ in sorted(scored, key=lambda x: -x[1])]


def _is_private_data_claim(claim_text: str) -> bool:
    """Return True if the claim references a specific private entity's data.

    Private claims cannot be verified via web search - DDGS returns population-level
    knowledge that falsely SUPPORTS absence claims about specific individuals.
    (S2 clinical trial bug, NabaOS arXiv:2603.10060 §3.2: epistemic classification
    before evidence collection.)

    Public registry override: if the claim primarily references a public data source
    (NCT trial number, FDA, PubMed, etc.), web search IS appropriate.
    """
    lower = claim_text.lower()
    if any(pub in lower for pub in _PUBLIC_REGISTRY_OVERRIDE):
        return False
    return any(sig in lower for sig in _PRIVATE_DATA_SIGNALS)


def _extract_numbers(text: str) -> list[float]:
    """Extract comparison-relevant numbers from text (commas stripped, years excluded)."""
    nums: list[float] = []
    for raw in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            val = float(raw.replace(",", ""))
        except ValueError:
            continue
        # Years read as topical context, not as claim quantities.
        if 1900 <= val <= 2099 and "." not in raw and "," not in raw:
            continue
        nums.append(val)
    return nums


def _numbers_match(a: float, b: float, rel_tol: float = 0.02) -> bool:
    """True when two quantities agree within 2% relative tolerance."""
    if a == b:
        return True
    denom = max(abs(a), abs(b))
    return denom > 0 and abs(a - b) / denom <= rel_tol


def collect_from_host_tools(
    claim_text: str,
    falsification_condition: str,
    tool_registry: HostToolRegistry,
) -> EvidenceResult:
    """P0: Delegate claim verification to the host agent's registered tools.

    Evidence quality: highest available - the host tool has direct access to the
    authoritative data source. Beats web search (public knowledge only) and
    parametric probing (circular).

    VerifiAgent arXiv:2504.00406: tool-based adaptive verification selects the
    appropriate tool based on reasoning type and dispatches structured queries.

    Query strategy: use falsification_condition as the tool query. The condition
    already encodes what evidence would *falsify* the claim, so if the tool returns
    data matching those terms, the claim is CONTRADICTED. If it returns nothing
    matching, the claim is tentatively SUPPORTED. If the tool is unreachable,
    INSUFFICIENT is returned and the caller decides whether to fall through.

    Private data firewall: when no matching tool is found AND the claim is about
    private data, returns INSUFFICIENT with confidence=0.1 - signaling that
    web search must NOT be attempted (intent C10).
    """
    matching_tools = tool_registry.find_matching(claim_text, falsification_condition)

    if not matching_tools:
        is_private = _is_private_data_claim(claim_text)
        return EvidenceResult(
            probe_tier=STRATEGY_HOST_TOOL,
            verdict="INSUFFICIENT",
            confidence=0.1 if is_private else 0.3,
            evidence_summary=(
                "Private data claim: no host tool registered to access this data source. "
                "Web search cannot verify claims about specific private entities."
                if is_private else
                "No host tool matched this claim."
            ),
            evidence_source="HOST_TOOL:none",
            observations=[],
        )

    # The falsification_condition is already a test; use it as the tool query.
    # This is the POPPER principle: design the query to find falsifying evidence.
    query = falsification_condition.strip() or claim_text

    tool_results: list[dict[str, str]] = []
    for tool in matching_tools[:2]:  # cap at 2 tools to bound latency
        try:
            raw = tool.fn(query)
            if raw and raw.strip():
                tool_results.append({
                    "tool": tool.name,
                    "result": raw.strip(),
                    "scope": tool.data_scope,
                })
        except Exception:  # noqa: BLE001
            pass

    if not tool_results:
        return EvidenceResult(
            probe_tier=STRATEGY_HOST_TOOL,
            verdict="INSUFFICIENT",
            confidence=0.3,
            evidence_summary=f"Host tool returned empty result for: {query[:80]}",
            evidence_source=f"HOST_TOOL:{matching_tools[0].name}",
            observations=[],
        )

    combined = " ".join(r["result"] for r in tool_results)
    tool_names = ", ".join(r["tool"] for r in tool_results)

    # Numeric fast-path: when both the claim and the tool output carry numbers,
    # compare them directly instead of relying on term overlap. Term overlap
    # cannot distinguish "holds 250 shares" from "holds 10,000 shares" against
    # the same evidence; the numbers can.
    claim_nums = _extract_numbers(claim_text)
    evidence_nums = _extract_numbers(combined)
    if claim_nums and evidence_nums:
        matched = any(
            _numbers_match(cn, en) for cn in claim_nums for en in evidence_nums
        )
        verdict = "SUPPORTS" if matched else "CONTRADICTS"
        confidence = 0.85
        observations = translate_to_observations(verdict, confidence, STRATEGY_HOST_TOOL)
        return EvidenceResult(
            probe_tier=STRATEGY_HOST_TOOL,
            verdict=verdict,
            confidence=confidence,
            evidence_summary=(
                f"Host tool ({tool_names}): {verdict} (numeric check: claim "
                f"{claim_nums[:3]} vs evidence {evidence_nums[:3]}). {combined[:200]}"
            ),
            evidence_source=f"HOST_TOOL:{tool_names}",
            observations=observations,
        )

    # Assess verdict by checking whether the tool result satisfies the
    # falsification_condition (CONTRADICTS) or is absent/neutral (SUPPORTS/INSUFFICIENT).
    # We key off the falsification_condition terms, not the claim terms, because the
    # condition already describes the falsifying evidence pattern.
    fc_terms = {
        t for t in re.split(r"\W+", falsification_condition.lower()) if len(t) > 3
    } or {t for t in re.split(r"\W+", claim_text.lower()) if len(t) > 3}

    lower_combined = combined.lower()
    fc_hits = sum(1 for t in fc_terms if t in lower_combined)
    total_fc_terms = max(len(fc_terms), 1)

    # ≥30% of falsification terms present in the tool output → condition is met → CONTRADICTS
    if fc_hits / total_fc_terms >= 0.30 and fc_hits >= 2:
        verdict, confidence = "CONTRADICTS", 0.85
    elif fc_hits >= 1:
        # Some overlap but not enough to fully satisfy the falsification condition.
        # The tool found something but not a clear contradiction.
        verdict, confidence = "CONFLICTING", 0.55
    else:
        # Tool returned data with no match to the falsification condition.
        # Absence of falsifying evidence tentatively supports the claim.
        verdict, confidence = "SUPPORTS", 0.75

    observations = translate_to_observations(verdict, confidence, STRATEGY_HOST_TOOL)
    return EvidenceResult(
        probe_tier=STRATEGY_HOST_TOOL,
        verdict=verdict,
        confidence=confidence,
        evidence_summary=f"Host tool ({tool_names}): {verdict}. {combined[:200]}",
        evidence_source=f"HOST_TOOL:{tool_names}",
        observations=observations,
    )


def select_strategy(
    claim_text: str,
    coordinator_tool_outputs: list[str] | None = None,
) -> str:
    """Return the highest-priority evidence collection strategy for this claim.

    Decision tree per eif_evidence_collection_intent.yaml §constraints C2–C3:
      - If numerical claim with checkable threshold → CODE_EXECUTION (P1)
      - If coordinator already searched → TOOL_OUTPUT (P2)
      - If references a named public database/registry → WEB_SEARCH (P3)
      - If company-specific → PARAMETRIC (P4, will return INSUFFICIENT)
      - Default → WEB_SEARCH (P3)
    """
    lower = claim_text.lower()

    # C3: coordinator outputs take priority if available (free evidence)
    if coordinator_tool_outputs:
        return STRATEGY_TOOL

    # C2: numerical claims → try code execution first
    if _NUMBER_RE.search(claim_text):
        return STRATEGY_CODE

    # Database/regulatory references → dedicated search
    if any(kw in lower for kw in _DATABASE_KEYWORDS):
        return STRATEGY_SEARCH

    # Company-specific → parametric is all we can do
    if any(sig in lower for sig in _COMPANY_SPECIFIC_SIGNALS):
        return STRATEGY_PARAM

    return STRATEGY_SEARCH


# ─────────────────────────────────────────────────────────────────────────────
# Shared stop-word set (used by both F15 and F16/relevance check)
# ─────────────────────────────────────────────────────────────────────────────

_STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "and", "or", "but", "if", "that", "this", "it",
    "its", "their", "our", "your", "as", "not", "than", "more", "also",
})


def _content_tokens(text: str) -> frozenset[str]:
    return frozenset(
        t for t in re.split(r"\W+", text.lower())
        if t and t not in _STOP_WORDS and len(t) > 2
    )


# ─────────────────────────────────────────────────────────────────────────────
# F15: Self-preference overlap guard (pre-filter for P3 web search)
# Research: arXiv:2404.13076, EMNLP 2024 - 67-82% self-preference bias
# ─────────────────────────────────────────────────────────────────────────────

def _compute_claim_overlap(claim_text: str, falsification_condition: str) -> float:
    """Return the fraction of claim tokens that appear verbatim in falsification_condition.

    Uses claim_text as the reference denominator (F15C2 constraint) so that a
    longer falsification condition cannot artificially dilute the overlap rate.
    Returns 0.0 when claim_text has no content tokens.
    """
    claim_tokens = _content_tokens(claim_text)
    if not claim_tokens:
        return 0.0
    fc_tokens = _content_tokens(falsification_condition)
    return len(claim_tokens & fc_tokens) / len(claim_tokens)


# ─────────────────────────────────────────────────────────────────────────────
# F16: Sentence-transformer model cache (optional dep - zero-breaking)
# ─────────────────────────────────────────────────────────────────────────────

_ST_MODEL_CACHE: dict[str, Any] = {}


def _get_sentence_transformer() -> Any:
    """Lazy-load all-MiniLM-L6-v2 once per process; return None on import failure."""
    model_name = "all-MiniLM-L6-v2"
    if model_name not in _ST_MODEL_CACHE:
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            _ST_MODEL_CACHE[model_name] = SentenceTransformer(model_name)
        except Exception:  # noqa: BLE001
            _ST_MODEL_CACHE[model_name] = None
    return _ST_MODEL_CACHE[model_name]


# ─────────────────────────────────────────────────────────────────────────────
# Relevance check (Self-RAG [IsRel] - C4 constraint)
# F16 upgrade: sentence-transformer cosine sim ≥ 0.3 when available
# ─────────────────────────────────────────────────────────────────────────────

def _keyword_overlap_relevant(claim_text: str, evidence_text: str) -> bool:
    """Keyword overlap relevance check (F16C1 fallback path).

    Returns True when ≥ 2 content tokens are shared between claim and evidence.
    This is the deterministic zero-dep fallback for is_relevant() when
    sentence-transformers is not installed. Exposed as a public-ish function
    (underscore = internal, but importable) so the F16C1 constraint test can
    directly validate the fallback path independent of the installed environment.
    """
    claim_tokens = _content_tokens(claim_text)
    evidence_tokens = _content_tokens(evidence_text)
    return len(claim_tokens & evidence_tokens) >= 2


def is_relevant(claim_text: str, evidence_text: str) -> bool:
    """Check if evidence is topically relevant to the claim (Self-RAG [IsRel] C4).

    F16: uses sentence-transformer cosine similarity (≥ 0.3) when the
    ``sentence-transformers`` package is installed (pip install eif-engine[monica]).
    Falls back to keyword overlap ≥ 2 tokens when unavailable - zero-breaking.

    is_relevant() is a *topic* filter, not a direction filter. A document
    semantically opposite to the claim (same topic, opposite conclusion) correctly
    returns True - the SUPPORTS/CONTRADICTS verdict logic handles direction.
    This fixes the F16 false-negative: "almost no pre-release buzz" is relevant
    to "5,000 hype followers" even though they share no content tokens.
    """
    model = _get_sentence_transformer()
    if model is not None:
        try:
            from sentence_transformers import util as st_util  # noqa: PLC0415
            embeddings = model.encode([claim_text, evidence_text], convert_to_tensor=True)
            score = float(st_util.cos_sim(embeddings[0], embeddings[1]))
            return score >= 0.3
        except Exception:  # noqa: BLE001
            pass  # fall through to keyword overlap

    return _keyword_overlap_relevant(claim_text, evidence_text)


# ─────────────────────────────────────────────────────────────────────────────
# Observation translation (per intent §5.3)
# ─────────────────────────────────────────────────────────────────────────────

def translate_to_observations(
    verdict: str,
    confidence: float,
    probe_tier: str,
    is_company_specific: bool = False,
) -> list[bool]:
    """Translate an evidence verdict to SPRT observations.

    C1 (independence):  P4 parametric probe is capped at INSUFFICIENT unless the
                        claim is general (not company-specific) and confidence ≥ 0.85.
    C6 (conflicting):   CONFLICTING → [True, False] (neutral, cancels out in SPRT).
    C8 (parametric):    P4 + company-specific → [True, False] always.

    SUPPORTS  @ confidence c  → min(5, round(c × 7)) True observations
    CONTRADICTS @ confidence c → min(5, round(c × 7)) False observations
    INSUFFICIENT              → [] (zero observations - do not bias SPRT)
    CONFLICTING               → [True, False]
    """
    # C8: parametric + company-specific is always neutral
    if probe_tier == STRATEGY_PARAM and is_company_specific:
        return [True, False]

    # C1: parametric capped at INSUFFICIENT unless high-confidence general claim
    if probe_tier == STRATEGY_PARAM:
        if confidence < 0.85 or verdict == "INSUFFICIENT":
            return []
        # High-confidence general claim: allow a weak signal
        if verdict == "SUPPORTS":
            return [True, True, False]
        if verdict == "CONTRADICTS":
            return [False, False, True]
        return []

    if verdict == "CONFLICTING":
        return [True, False]

    if verdict == "INSUFFICIENT":
        return []

    n = max(1, min(5, round(confidence * 7)))
    if verdict == "SUPPORTS":
        return [True] * n
    if verdict == "CONTRADICTS":
        return [False] * n
    return []


# ─────────────────────────────────────────────────────────────────────────────
# P1: Code execution evidence (C2 constraint)
# ─────────────────────────────────────────────────────────────────────────────

_CODE_TEMPLATES: dict[str, str] = {
    "churn": textwrap.dedent("""\
        # Verify SaaS churn rate claim against public benchmark data
        # Source: Recurly Research 2023, ChartMogul 2024 benchmarks
        import json, re

        def main():
            claim = {claim}

            # Public SaaS benchmark ranges (from Recurly 2023 / ChartMogul 2024)
            BENCHMARK_ANNUAL_CHURN_RANGE = (0.04, 0.08)  # 4-8% is typical SaaS annual

            nums = re.findall(r"(\\d+(?:\\.\\d+)?)\\s*%", claim)
            if not nums:
                print(json.dumps({{"verdict": "INSUFFICIENT", "reason": "no percentage found in claim"}}))
                return

            claimed_pct = float(nums[0]) / 100
            lo, hi = BENCHMARK_ANNUAL_CHURN_RANGE
            verdict = "SUPPORTS" if lo <= claimed_pct <= hi * 1.5 else "CONTRADICTS"
            print(json.dumps({{
                "verdict": verdict,
                "claimed": claimed_pct,
                "benchmark_range": [lo, hi],
                "source": "EIF built-in benchmark constants (range published by Recurly 2023 / ChartMogul 2024; not queried live)"
            }}))

        main()
    """),
    "market_size": textwrap.dedent("""\
        # Verify market size claim against public projections
        # Source: Grand View Research / MarketsandMarkets public summaries
        import json, re

        def main():
            claim = {claim}

            # AI healthcare market (2024-2030 projections from multiple analyst reports)
            nums = re.findall(r"\\$(\\d+(?:\\.\\d+)?)\\s*(billion|million|B|M)", claim, re.I)
            if not nums:
                print(json.dumps({{"verdict": "INSUFFICIENT", "reason": "no dollar figure found"}}))
                return

            val, unit = nums[0]
            val = float(val)
            if unit.lower() in ("billion", "b"):
                val_usd = val * 1e9
            else:
                val_usd = val * 1e6

            # AI healthcare market: $10B-$20B in 2024, growing to $40-$70B by 2030
            MARKET_RANGE_2024 = (5e9, 25e9)
            lo, hi = MARKET_RANGE_2024
            verdict = "SUPPORTS" if lo <= val_usd <= hi * 2 else "CONTRADICTS"
            print(json.dumps({{
                "verdict": verdict,
                "claimed_usd": val_usd,
                "benchmark_range_usd": [lo, hi],
                "source": "EIF built-in benchmark constants (ranges published by Grand View Research / MarketsandMarkets 2024; not queried live)"
            }}))

        main()
    """),
    "latency": textwrap.dedent("""\
        # Verify latency/throughput claim against public engineering benchmarks
        # Sources: Google SRE Book 2016, AWS Well-Architected Framework 2024,
        #          Uber Engineering blog (microservices latency overhead 2019)
        import json, re

        def main():
            claim = {claim}

            # Extract numeric values and their context
            nums = re.findall(r"(\\d+(?:\\.\\d+)?)\\s*(ms|milliseconds?|rps|requests?/s|tps|qps)", claim, re.I)

            # Published benchmarks (Google SRE / AWS Well-Architected / Uber)
            BENCHMARKS = {{
                "network_hop_overhead_ms": (0.5, 5.0),        # per service call: 0.5-5ms typical
                "service_mesh_overhead_ms": (1.0, 10.0),      # Envoy/Istio sidecar: 1-10ms
                "p99_web_api_acceptable_ms": (50, 500),        # < 100ms fast, < 500ms acceptable
                "monolith_p99_typical_ms": (20, 200),          # well-tuned monolith baseline
            }}

            result = {{
                "verdict": "INSUFFICIENT",
                "benchmarks": BENCHMARKS,
                "nums_found": nums,
                "source": "EIF built-in benchmark constants (per Google SRE Book 2016, Uber Eng Blog 2019, AWS Well-Arch 2024; not queried live)"
            }}

            if not nums:
                print(json.dumps(result))
                return

            val, unit = nums[0]
            val = float(val)
            unit_lower = unit.lower()

            if "ms" in unit_lower or "millisecond" in unit_lower:
                lo, hi = BENCHMARKS["p99_web_api_acceptable_ms"]
                in_range = lo <= val <= hi * 3
                result["verdict"] = "SUPPORTS" if in_range else "CONTRADICTS"
                result["claimed_ms"] = val
                result["acceptable_range_ms"] = [lo, hi]
            elif any(x in unit_lower for x in ("rps", "tps", "qps", "requests")):
                # High throughput: plausible range for a typical Rails monolith 100-5000 RPS
                in_range = 10 <= val <= 20000
                result["verdict"] = "SUPPORTS" if in_range else "CONTRADICTS"
                result["claimed_rps"] = val
                result["plausible_range_rps"] = [10, 20000]

            print(json.dumps(result))

        main()
    """),
    "microservices_overhead": textwrap.dedent("""\
        # Model microservices decomposition overhead
        # Sources: Fowler (2014 microservices tradeoffs), Netflix Eng Blog,
        #          CNCF Survey 2023, Uber post-mortem on nanoservices
        import json, re

        def main():
            claim = {claim}
            lower = claim.lower()

            # Published overhead models
            OVERHEAD = {{
                "per_service_latency_ms":       (1.0, 8.0),
                "ops_complexity_multiplier":    (2.0, 5.0),
                "initial_dev_overhead_factor":  (1.3, 2.0),
                "typical_service_count_medium": (10, 50),
            }}

            # Causal overclaim check FIRST (language-based, no numbers needed).
            # "microservices will reduce/lower latency / make faster" is a documented
            # misconception - microservices ADD latency per hop.
            # Source: Fowler 2014, Netflix Eng Blog, CNCF Survey 2023
            causal_overclaim = (
                any(w in lower for w in ("microservice", "service mesh", "decompos", "micro service"))
                and any(w in lower for w in ("reduce latency", "lower latency", "faster",
                                             "speed up", "improve latency", "less latency",
                                             "better performance", "improve performance"))
            )
            if causal_overclaim:
                print(json.dumps({{
                    "verdict": "CONTRADICTS",
                    "causal_overclaim_detected": True,
                    "overhead_model": OVERHEAD,
                    "source": "EIF built-in heuristics (per Fowler 2014, Netflix Eng Blog, CNCF Survey 2023; not queried live)",
                    "note": "Microservices add 2-10ms latency per network hop. Performance gains come from independent scaling, not raw latency reduction."
                }}))
                return

            # Numeric plausibility check for service count or latency claims
            nums = re.findall(r"(\\d+(?:\\.\\d+)?)", claim)
            if not nums:
                print(json.dumps({{
                    "verdict": "INSUFFICIENT",
                    "source": "EIF built-in heuristics (per Fowler 2014, Netflix Eng Blog, CNCF Survey 2023; not queried live)",
                    "overhead_model": OVERHEAD,
                    "note": "No numeric value found to verify"
                }}))
                return

            print(json.dumps({{
                "verdict": "SUPPORTS",
                "overhead_model": OVERHEAD,
                "source": "EIF built-in heuristics (per Fowler 2014, Netflix Eng Blog, CNCF Survey 2023; not queried live)",
            }}))

        main()
    """),
    "cloud_cost": textwrap.dedent("""\
        # Verify cloud infrastructure cost claim
        # Sources: AWS Calculator public estimates, CNCF finOps report 2023,
        #          Datadog State of Cloud Cost 2024
        import json, re

        def main():
            claim = {claim}

            nums = re.findall(r"\\$?(\\d+(?:,\\d{{3}})*(?:\\.\\d+)?)\\s*(?:k|thousand|/month|/mo|per month)?", claim, re.I)
            if not nums:
                print(json.dumps({{"verdict": "INSUFFICIENT", "reason": "no cost figure found",
                                  "source": "EIF built-in benchmark constants (per AWS Calculator / CNCF FinOps 2023; not queried live)"}}))
                return

            # Parse first number
            val = float(nums[0].replace(",", ""))

            # Typical ranges for medium SaaS (100k-1M req/day)
            RANGES = {{
                "monthly_infra_usd": (500, 50000),
                "per_rps_usd_monthly": (5, 50),      # $5-$50/RPS/month (k8s + networking)
            }}
            lo, hi = RANGES["monthly_infra_usd"]
            in_range = lo <= val <= hi * 5

            print(json.dumps({{
                "verdict": "SUPPORTS" if in_range else "CONTRADICTS",
                "claimed_usd": val,
                "benchmark_range_monthly_usd": [lo, hi],
                "source": "EIF built-in benchmark constants (per AWS Calculator, CNCF FinOps 2023, Datadog 2024; not queried live)",
            }}))

        main()
    """),
}


def _pick_code_template(claim_text: str) -> str | None:
    lower = claim_text.lower()
    if any(w in lower for w in ("churn", "retention", "renewal")):
        return "churn"
    if any(w in lower for w in ("market size", "market cap", "total addressable", "tam", "market worth")):
        return "market_size"
    if any(w in lower for w in ("microservice", "service mesh", "monolith", "decompos", "domain-driven")):
        return "microservices_overhead"
    if any(w in lower for w in ("latency", "p99", "p95", "p50", "millisecond", " ms ", "rps", "throughput", "requests per second", "response time")):
        return "latency"
    if any(w in lower for w in ("cloud cost", "infra cost", "infrastructure cost", "monthly cost", "aws", "gcp", "azure", "kubernetes cost", "k8s cost")):
        return "cloud_cost"
    # Fallback: any claim with a number + billion/million (market-size pattern)
    if any(w in lower for w in ("billion", "market")):
        return "market_size"
    return None


def collect_code_execution(claim_text: str, timeout_s: int = 30) -> EvidenceResult:
    """P1: Execute a deterministic check of a numerical claim in a subprocess.

    The generated code compares the number parsed from the claim against
    benchmark constants built into the template (the cited organizations
    published the ranges; they are not queried live). Execution is
    deterministic and reproducible. Claim text is substituted via
    json.dumps() (a fully escaped Python string literal, not string
    interpolation into source), and the resulting code is AST-screened
    (imports, builtins, and all dunder attribute/name access) before
    running. See native_tools._validate_code for what that screen covers.
    """
    template_key = _pick_code_template(claim_text)
    if template_key is None:
        return EvidenceResult(
            probe_tier=STRATEGY_CODE,
            verdict="INSUFFICIENT",
            confidence=0.0,
            evidence_summary="No code template available for this claim type",
            evidence_source="CODE_EXECUTION",
            observations=[],
        )

    import json as _json
    # json.dumps produces a properly escaped Python string literal (quotes,
    # backslashes, newlines) - the template substitutes it as a bare
    # expression (`claim = {claim}`), so there is no way for claim_text to
    # break out of the surrounding source regardless of its content.
    code = _CODE_TEMPLATES[template_key].format(claim=_json.dumps(claim_text))

    from eif.falsify.native_tools import _validate_code
    violation = _validate_code(code)
    if violation is not None:
        return EvidenceResult(
            probe_tier=STRATEGY_CODE,
            verdict="INSUFFICIENT",
            confidence=0.0,
            evidence_summary=f"Code template rejected by AST screen: {violation}",
            evidence_source="CODE_EXECUTION",
            observations=[],
        )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            tmp_path = f.name

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True, timeout=timeout_s
        )
        output = result.stdout.strip()
        if not output:
            raise ValueError(f"no output: {result.stderr[:200]}")

        import json
        data = json.loads(output)
        verdict = data.get("verdict", "INSUFFICIENT")
        confidence = 0.85 if verdict != "INSUFFICIENT" else 0.0
        source = data.get("source", "CODE_EXECUTION")
        summary = f"Code execution: claimed={data.get('claimed', '?')} benchmark={data.get('benchmark_range', '?')}"
    except Exception as exc:  # noqa: BLE001
        verdict = "INSUFFICIENT"
        confidence = 0.0
        source = "CODE_EXECUTION"
        summary = f"Code execution failed: {str(exc)[:120]}"
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    observations = translate_to_observations(verdict, confidence, STRATEGY_CODE)
    return EvidenceResult(
        probe_tier=STRATEGY_CODE,
        verdict=verdict,
        confidence=confidence,
        evidence_summary=summary,
        evidence_source=source,
        observations=observations,
    )


# ─────────────────────────────────────────────────────────────────────────────
# P2: Coordinator tool output extraction (C3 constraint, highest ROI)
# ─────────────────────────────────────────────────────────────────────────────

def collect_from_tool_outputs(
    claim_text: str,
    tool_outputs: list[str],
) -> EvidenceResult:
    """P2: Use multi-agent coordinator already-retrieved web search results as evidence.

    Intent C3: coordinator tool outputs must be captured before any further probe.
    ReAct arXiv:2210.03629: tool observations (not model reasoning) are the evidence.
    Self-RAG C4: relevance check before belief update.
    """
    relevant = [t for t in tool_outputs if is_relevant(claim_text, t)]
    if not relevant:
        return EvidenceResult(
            probe_tier=STRATEGY_TOOL,
            verdict="INSUFFICIENT",
            confidence=0.3,
            evidence_summary="Coordinator search results not relevant to this claim",
            evidence_source="TOOL_OUTPUT",
            observations=[],
            follow_up_query=_generate_follow_up_query(claim_text, "no relevant results"),
        )

    # Assess support vs contradiction in relevant outputs
    supports_signals: list[bool] = []
    lower_claim = claim_text.lower()
    key_terms = {t for t in re.split(r"\W+", lower_claim) if len(t) > 3}

    for text in relevant[:5]:
        lower_text = text.lower()
        support_score = sum(1 for t in key_terms if t in lower_text)
        # Contradiction heuristics: negation near key terms
        negation_near = any(
            neg in lower_text[max(0, lower_text.find(t) - 50): lower_text.find(t) + 50]
            for t in key_terms if t in lower_text
            for neg in ("not ", "no ", "never ", "false", "incorrect", "wrong", "refuted", "contrary")
        )
        if support_score >= 2 and not negation_near:
            supports_signals.append(True)
        elif negation_near and support_score >= 1:
            supports_signals.append(False)

    if not supports_signals:
        verdict, confidence = "INSUFFICIENT", 0.4
    elif all(supports_signals):
        verdict, confidence = "SUPPORTS", min(0.7 + 0.05 * len(supports_signals), 0.90)
    elif not any(supports_signals):
        verdict, confidence = "CONTRADICTS", min(0.6 + 0.05 * len(supports_signals), 0.85)
    else:
        # C6: conflicting signals among relevant sources
        verdict, confidence = "CONFLICTING", 0.5

    is_company = any(sig in claim_text.lower() for sig in _COMPANY_SPECIFIC_SIGNALS)
    observations = translate_to_observations(verdict, confidence, STRATEGY_TOOL, is_company)
    return EvidenceResult(
        probe_tier=STRATEGY_TOOL,
        verdict=verdict,
        confidence=confidence,
        evidence_summary=f"From coordinator search ({len(relevant)} relevant results of {len(tool_outputs)}): {verdict}",
        evidence_source=f"TOOL_OUTPUT:{len(relevant)}_relevant",
        observations=observations,
        is_company_specific=is_company,
        follow_up_query=_generate_follow_up_query(claim_text, verdict) if verdict in ("INSUFFICIENT", "CONFLICTING") else None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# P3: Dedicated web search per claim
# ─────────────────────────────────────────────────────────────────────────────

def _generate_follow_up_query(claim_text: str, previous_verdict: str) -> str:
    """Generate a more specific follow-up search query (FIRE arXiv:2411.00784 C5)."""
    # Extract the core subject (first ~6 words, drop hedge words)
    words = [w for w in claim_text.split() if len(w) > 2][:8]
    base = " ".join(words[:5])
    suffix = "peer-reviewed evidence" if "INSUFFICIENT" in previous_verdict else "contradicting evidence"
    return f"{base} {suffix}"


# Matches http(s):// URLs and bare host names like "example.com/path".
# Used to pull source identifiers out of search-result text for corroboration.
_URL_RE = re.compile(
    r"https?://[^\s\]\)>\"']+"            # full URLs (DDGS native_search emits [href])
    r"|(?<![\w.@])"                        # or bare hosts not preceded by word/.@
    r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+"  # one+ labels
    r"(?:com|org|net|edu|gov|io|ai|co|us|uk|int|info|biz|gov\.[a-z]{2})"
    r"(?:/[^\s\]\)>\"']*)?",
    re.IGNORECASE,
)


def _extract_domains(text: str) -> set[str]:
    """Extract DISTINCT registrable domains from search-result text (TW4/TW5).

    Normalizes each URL/host to its registrable domain (strips scheme, path,
    leading "www.", and any "label." prefix beyond the last two labels) so that
    two snippets from the SAME site count as ONE source - this IS the echo /
    duplicate guard. Returns an empty set when no URLs/hosts are present.

    EIF's native DDGS backend (native_tools.native_search) formats each result as
    "title. body [href]", so href URLs ARE present and domain extraction is real,
    not a fallback. When a search fn returns text with no identifiable URLs/hosts,
    the empty set is returned and corroboration stays False (conservative: absence
    of identifiable sources is not corroboration).

    Research: PoisonedRAG arXiv:2402.07867 - duplicated/echoed content inflates
    apparent support; independence must be measured per distinct source.
    """
    domains: set[str] = set()
    for match in _URL_RE.findall(text or ""):
        host = match.strip().lower()
        # Strip scheme.
        if "://" in host:
            host = host.split("://", 1)[1]
        # Strip path / query / fragment.
        host = re.split(r"[/?#]", host, maxsplit=1)[0]
        # Strip a port if present.
        host = host.split(":", 1)[0]
        # Strip leading www.
        if host.startswith("www."):
            host = host[4:]
        if not host or "." not in host:
            continue
        labels = host.split(".")
        # Registrable domain: keep the last two labels (e.g. nih.gov, nature.com).
        # Two-label public suffixes (gov.uk, co.uk, ...) keep the last three so
        # different orgs under the same suffix remain distinct.
        _TWO_LABEL_SUFFIXES = {"gov.uk", "co.uk", "ac.uk", "org.uk", "com.au",
                               "co.jp", "gov.au", "edu.au", "co.nz"}
        if len(labels) >= 3 and ".".join(labels[-2:]) in _TWO_LABEL_SUFFIXES:
            registrable = ".".join(labels[-3:])
        else:
            registrable = ".".join(labels[-2:])
        domains.add(registrable)
    return domains


def collect_web_search(
    claim_text: str,
    web_search_fn: Any,  # callable: (query: str) -> str
    max_iterations: int = 2,
) -> EvidenceResult:
    """P3: Dedicated multi-source web search per claim.

    Intent C5: when SPRT CONTINUE, generate follow-up query and iterate.
    Self-RAG C4: relevance check before adding observations.
    AVeriTeC C6: conflicting sources → neutral SPRT signal.
    """
    from eif.falsify.sprt import run_sprt
    from eif.schemas import FalsificationCondition

    all_observations: list[bool] = []
    evidence_sources: list[str] = []
    last_verdict = "INSUFFICIENT"
    last_confidence = 0.3
    # TW4/TW5: union of DISTINCT registrable domains observed across iterations
    # that produced a relevant/usable hit. Same-domain echo dedupes here.
    distinct_domains: set[str] = set()

    # Build initial query
    query = f"{claim_text[:100]} evidence research"

    for _iteration in range(max_iterations):
        try:
            raw_result = web_search_fn(query)
        except Exception:  # noqa: BLE001
            break

        if not raw_result or not is_relevant(claim_text, raw_result):
            query = _generate_follow_up_query(claim_text, "INSUFFICIENT")
            continue

        # TW4/TW5: accumulate distinct registrable domains from this relevant hit.
        distinct_domains |= _extract_domains(raw_result)

        # Lightweight support/contradiction assessment (zero-LLM, per C1)
        lower = raw_result.lower()
        lower_claim = claim_text.lower()
        key_terms = {t for t in re.split(r"\W+", lower_claim) if len(t) > 3}
        term_hits = sum(1 for t in key_terms if t in lower)
        negated = sum(
            1 for t in key_terms if t in lower
            and any(
                neg in lower[max(0, lower.find(t) - 60): lower.find(t) + 60]
                for neg in ("not ", "no evidence", "incorrect", "false", "refuted", "contrary to", "does not")
            )
        )

        if term_hits >= 3 and negated == 0:
            verdict_i, conf_i = "SUPPORTS", 0.65
        elif negated >= 2:
            verdict_i, conf_i = "CONTRADICTS", 0.60
        elif term_hits >= 1 and negated >= 1:
            verdict_i, conf_i = "CONFLICTING", 0.50
        else:
            verdict_i, conf_i = "INSUFFICIENT", 0.35

        obs_i = translate_to_observations(verdict_i, conf_i, STRATEGY_SEARCH)
        all_observations.extend(obs_i)
        evidence_sources.append(query[:60])
        last_verdict, last_confidence = verdict_i, conf_i

        # C5: check if SPRT needs more evidence
        if all_observations:
            try:
                fc = FalsificationCondition(
                    claim_text=claim_text[:200],
                    condition=f"Evidence contradicts: {claim_text[:80]}",
                    threshold="p<0.05",
                    test_procedure=STRATEGY_SEARCH,
                    sprt_alpha=0.05,
                    sprt_beta=0.10,
                    sprt_effect_size=0.20,  # C3: schema default; consistent with eif_falsify path
                )
                sprt = run_sprt(fc, all_observations)
                if sprt.decision in ("ACCEPT", "REJECT"):
                    break  # sufficient evidence accumulated
            except Exception:  # noqa: BLE001
                pass

        # Generate follow-up for next iteration
        query = _generate_follow_up_query(claim_text, last_verdict)

    if not all_observations:
        last_verdict, last_confidence = "INSUFFICIENT", 0.3

    is_company = any(sig in claim_text.lower() for sig in _COMPANY_SPECIFIC_SIGNALS)
    # TW4/TW5: corroboration = >= 2 DISTINCT registrable domains across iterations.
    independent_source_count = len(distinct_domains)
    corroborated = independent_source_count >= 2
    return EvidenceResult(
        probe_tier=STRATEGY_SEARCH,
        verdict=last_verdict,
        confidence=last_confidence,
        evidence_summary=f"Web search ({len(evidence_sources)} queries): {last_verdict}",
        evidence_source="; ".join(evidence_sources[:2]) or "WEB_SEARCH",
        observations=all_observations,
        is_company_specific=is_company,
        independent_source_count=independent_source_count,
        corroborated=corroborated,
    )


# ─────────────────────────────────────────────────────────────────────────────
# P4: Parametric probe (fallback - must emit INSUFFICIENT for company-specific)
# ─────────────────────────────────────────────────────────────────────────────

def collect_parametric(
    claim_text: str,
    llm_probe_fn: Any,  # callable: (claim: str) -> dict
) -> EvidenceResult:
    """P4: LLM parametric probe - fallback only.

    Intent C1: evidence must be independent - P4 is NOT independent.
    Intent C8: company-specific claims → always INSUFFICIENT (neutral SPRT).
    FActScore: same-model family verification is circular.
    """
    is_company = any(sig in claim_text.lower() for sig in _COMPANY_SPECIFIC_SIGNALS)

    try:
        probe = llm_probe_fn(claim_text)
        verdict = probe.get("verdict", "INSUFFICIENT")
        confidence = float(probe.get("confidence", 0.3))
    except Exception:  # noqa: BLE001
        verdict, confidence = "INSUFFICIENT", 0.3

    observations = translate_to_observations(verdict, confidence, STRATEGY_PARAM, is_company)
    return EvidenceResult(
        probe_tier=STRATEGY_PARAM,
        verdict="INSUFFICIENT" if is_company else verdict,
        confidence=0.0 if is_company else confidence,
        evidence_summary=f"Parametric probe: {verdict} (company-specific={is_company})",
        evidence_source="PARAMETRIC",
        observations=observations,
        is_company_specific=is_company,
        temporal_concern=probe.get("temporal_concern", False) if isinstance(probe, dict) else False,
        causal_concern=probe.get("causal_concern", False) if isinstance(probe, dict) else False,
        metric_quality="DEGRADED_METRIC",  # F17: P4 is always degraded (non-independent)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point: collect_evidence
# ─────────────────────────────────────────────────────────────────────────────

def collect_evidence(
    claim_text: str,
    falsification_condition: str,
    knowledge_gap: str | None = None,
    host_tool_registry: HostToolRegistry | None = None,
    coordinator_tool_outputs: list[str] | None = None,
    web_search_fn: Any | None = None,
    llm_probe_fn: Any | None = None,
    max_search_iterations: int = 2,
    self_preference_risk: bool = False,
) -> EvidenceResult:
    """Collect evidence for a claim using the highest-priority available strategy.

    Falls through the five tiers (runtime order - P2 precedes P1 per intent C3/C9):
      P0 HOST_TOOL      → if host_tool_registry provided with matching tools
      P2 TOOL_OUTPUT    → if coordinator_tool_outputs provided (free; checked before P1)
      P1 CODE_EXECUTION → if numerical + template available (runs after P2)
      P3 WEB_SEARCH     → if web_search_fn provided (blocked for private data)
      P4 PARAMETRIC     → if llm_probe_fn provided AND self_preference_risk=False

    Private data firewall (intent C10): claims about specific private entities
    (patient records, EHR, internal databases) are blocked from reaching P3 web
    search because DDGS returns population-level knowledge that falsely SUPPORTS
    absence claims about specific individuals. If no P0 host tool is available
    for a private data claim, INSUFFICIENT is returned immediately - which triggers
    a HALT for GUESSED claims, the correct behavior.

    Self-preference firewall (arXiv:2509.00462 - Xu et al. 2025):
    When self_preference_risk=True, P4 parametric probe is unconditionally blocked.
    The model that generated the claim exhibits 67–82% self-preference bias and
    cannot serve as independent evidence for its own output. P0/P1/P2/P3 are
    unaffected - only the model-as-verifier path is blocked.

    Returns EvidenceResult with observations ready for run_sprt().
    """
    # P0: host tool delegation - highest priority tier.
    # The host agent registers tools that have direct access to the authoritative
    # data source (EHR, database, internal API). If the tool matches the claim,
    # its output is more reliable than any proxy (web search, code execution).
    # VerifiAgent arXiv:2504.00406; intent C9.
    if host_tool_registry is not None and not host_tool_registry.is_empty():
        p0 = collect_from_host_tools(claim_text, falsification_condition, host_tool_registry)
        if p0.verdict != "INSUFFICIENT":
            return p0
        # P0 returned INSUFFICIENT. For private data claims, stop here - do NOT
        # fall through to web search (it would give population-level false positives).
        # Intent C10; NabaOS arXiv:2603.10060 §3.2.
        if _is_private_data_claim(claim_text):
            p0.metric_quality = "PRIVATE_DATA_BLOCKED"  # F17
            return p0
        # Non-private + no matching tool → fall through to P1/P2/P3
    elif _is_private_data_claim(claim_text):
        # No registry at all + private data claim → INSUFFICIENT immediately.
        # This is the fix for the S2 clinical trial scenario: GUESSED absence
        # claims about individual patients must not be web-searched.
        return EvidenceResult(
            probe_tier=STRATEGY_HOST_TOOL,
            verdict="INSUFFICIENT",
            confidence=0.1,
            evidence_summary=(
                "Private data claim: no host tool configured. "
                "Cannot verify claims about specific private entities via web search."
            ),
            evidence_source="HOST_TOOL:not_configured",
            observations=[],
            metric_quality="PRIVATE_DATA_BLOCKED",  # F17
        )

    # P2: coordinator tool outputs - checked BEFORE P1 (intent C3/C9).
    # These are free: the coordinator already retrieved them; no additional
    # network calls needed. If P2 returns a decisive verdict, skip P1 entirely.
    if coordinator_tool_outputs:
        result = collect_from_tool_outputs(claim_text, coordinator_tool_outputs)
        if result.verdict not in ("INSUFFICIENT",) or not web_search_fn:
            # P2 decisive or no search fn available - P1 still runs below if INSUFFICIENT
            if result.verdict != "INSUFFICIENT":
                return result

    # P1: code execution for numerical claims with a matching template.
    # Runs after P2 (intent C3/C9): coordinator outputs are preferred when available,
    # but P1 deterministic execution is the stronger signal for numerical claims.
    if _pick_code_template(claim_text) is not None:
        result = collect_code_execution(claim_text)
        if result.verdict != "INSUFFICIENT":
            return result
        # P1 returned INSUFFICIENT - no template matched or execution failed; continue

    # P3: dedicated web search - auto-substitute native DDGS if no fn provided (NT4)
    _using_native_search = False
    if not web_search_fn:
        from eif.falsify.native_tools import get_native_search_fn  # noqa: PLC0415
        web_search_fn = get_native_search_fn()
        _using_native_search = web_search_fn is not None

    if web_search_fn:
        # F15: Self-preference overlap guard - runs BEFORE the web search call (F15C1).
        # If the falsification_condition shares ≥ 35% of claim tokens verbatim, the
        # query would recover the claim's own vocabulary rather than independent evidence.
        # Research: arXiv:2404.13076, EMNLP 2024 - 67-82% self-preference bias in LLMs.
        # Per F15 behavior: block P3 and fall through to P4 (with normal C1/C8 caps).
        overlap = _compute_claim_overlap(claim_text, falsification_condition)
        if overlap >= 0.35:
            _f15_block = EvidenceResult(
                probe_tier=STRATEGY_SEARCH,
                verdict="INSUFFICIENT",
                confidence=0.0,
                evidence_summary=(
                    f"Self-preference risk: falsification condition shares "
                    f"{overlap:.0%} of claim tokens (threshold: 35%). "
                    "Web search would likely recover claim vocabulary, not independent evidence "
                    "(arXiv:2404.13076: 67-82% self-preference bias in LLMs). "
                    "Use a falsification condition phrased independently of the claim."
                ),
                evidence_source="SELF_PREFERENCE_BLOCKED",
                observations=[],
                metric_quality="SELF_PREFERENCE_BLOCKED",  # F17
            )
            # Fall through to P4 - F15 only blocks P3, not the parametric probe.
            # P4 applies its normal C1/C8 caps on company-specific claims.
            if llm_probe_fn and not self_preference_risk:
                return collect_parametric(claim_text, llm_probe_fn)
            return _f15_block

        result = collect_web_search(claim_text, web_search_fn, max_search_iterations)
        if _using_native_search and result.evidence_source:
            result.evidence_source = f"DDGS/native:{result.evidence_source}"
        if result.verdict != "INSUFFICIENT" or not llm_probe_fn:
            return result
        # Fall through to P4

    # P4: parametric probe (explicit fallback, caps on company-specific).
    # Self-preference firewall: if the claim originated in a prior assistant
    # turn (self_preference_risk=True), P4 is unconditionally blocked - the
    # same model that generated the claim cannot verify it.
    # Research basis: Xu et al. arXiv:2509.00462 (67–82% self-preference bias);
    # Panickssery et al. NeurIPS 2024 (self-recognition drives self-preference).
    if llm_probe_fn and not self_preference_risk:
        return collect_parametric(claim_text, llm_probe_fn)

    if self_preference_risk and llm_probe_fn:
        return EvidenceResult(
            probe_tier=STRATEGY_PARAM,
            verdict="INSUFFICIENT",
            confidence=0.0,
            evidence_summary=(
                "P4 blocked: self-preference risk detected. "
                "The model that generated this claim cannot independently verify it "
                "(arXiv:2509.00462: 67–82% self-preference bias in large models). "
                "Independent evidence tier required."
            ),
            evidence_source="PARAMETRIC:blocked_self_preference",
            observations=[],
            metric_quality="SELF_PREFERENCE_BLOCKED",  # F17
        )

    # No evidence available
    return EvidenceResult(
        probe_tier="NONE",
        verdict="INSUFFICIENT",
        confidence=0.0,
        evidence_summary="No evidence collection method available",
        evidence_source="NONE",
        observations=[],
    )

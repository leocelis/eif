# EIF CAUSAL_GATE v4 - Technical Specification

> **Historical design note.** This document is the original implementation spec,
> kept for provenance. File paths and status lines reflect the tree at writing
> time; the current architecture reference is [architecture.md](architecture.md).


**Version**: 1.0 (draft)  
**Date**: 2026-05-08  
**Intent artifact**: `eif/causal_gate/eif_causal_gate_v4_intent.yaml`  
**Depends on**: EIF v3.1 (INPUT_GUARD, native_tools.py)

---

## 1. Summary

CAUSAL_GATE v4 adds a **Causal Evidence Probe (CEP)** that fires when a HIGH-consequence
claim is classified at Pearl's INTERVENTION or COUNTERFACTUAL level. Instead of just
flagging the causal overclaim, CEP searches for independent causal evidence (RCTs,
meta-analyses, natural experiments) and returns a structured `CausalVerdict` that
feeds into CALIBRATE's posterior update.

This closes the last structural gap between EIF and the scientific method: causal
claims are now tested against external evidence, not merely identified.

---

## 2. Background & Research

### 2.1 The Problem (What LLMs Get Wrong)

| Failure mode | Source | Finding |
|---|---|---|
| Rung Collapse | ERM (arXiv:2602.11675, 2025) | LLMs substitute P(Y\|X) for P(Y\|do(X)) - confuse observation with intervention |
| Real-world causal inference | ReCITE (arXiv:2505.18931, 2025) | Best model F1=0.535 on real causal extraction - barely above chance |
| Conjunctive → disjunctive | arXiv:2505.09614, 2025 | LLMs treat "A AND B cause C" as "A OR B cause C" |
| Reasoning Theater | Ariadne (arXiv:2601.02314, 2026) | Correct conclusions from contradictory internal logic; reasoning traces are unfaithful |
| Multi-agent debate ceiling | CRAwDAD (arXiv:2511.22854, 2025) | Debate improves 78%→87% on CLadder, but still 13% error on counterfactuals |

### 2.2 The Design Insight

We do NOT attempt to:
- Build causal DAGs from conversation text (requires domain-specific structural models)
- Run do-calculus programmatically (requires known graph structure)
- Use LLM judgment as causal evidence (that's P4 - circular)

We DO:
- Search for whether the causal question has already been answered by the scientific community
- Treat "no RCT/meta-analysis found" as information (verdict: NO_EVIDENCE)
- Treat "RCT found supporting opposite direction" as REVERSED
- Feed the verdict into the same Bayesian pipeline everything else uses

This mirrors real scientific practice: before designing a new experiment, check
if the question was already settled.

### 2.3 Trusted Libraries (Reference, Not Runtime)

| Library | GitHub | Stars | Use |
|---|---|---|---|
| DoWhy (py-why/dowhy) | py-why/dowhy | 8,049 | Vocabulary reference: refutation patterns, causal effect estimation API design |
| causal-learn (py-why/causal-learn) | py-why/causal-learn | 1,579 | DAG structure pattern reference |

Neither is a runtime dependency. CEP reuses `native_tools.composed_search` for P3.

---

## 3. Architecture

### 3.1 Trigger Condition

```
IF claim.causal_level IN (INTERVENTION, COUNTERFACTUAL)
   AND claim.consequence_of_wrong == HIGH
THEN run_causal_evidence_probe(claim)
ELSE return existing v3 flag (no change to current behavior)
```

LOW/MEDIUM claims and ASSOCIATION-level claims are unaffected.

### 3.2 Flow

```
┌──────────────────────────────────────────────────────────────┐
│ CAUSAL_GATE v3 (unchanged)                                   │
│   classify_causal_level() → ASSOCIATION / INTERVENTION / CF  │
│   check_confounders() → undocumented confounders             │
│   check_direction() → temporal ordering heuristic            │
│   check_intervention() → level mismatch flag                 │
└────────────────────┬─────────────────────────────────────────┘
                     │ (HIGH + INTERVENTION/CF)
                     ▼
┌──────────────────────────────────────────────────────────────┐
│ CAUSAL_GATE v4 - Causal Evidence Probe (CEP)                 │
│                                                              │
│  1. extract_causal_pair(claim) → (cause, effect, domain)     │
│  2. formulate_search_query(cause, effect, domain)            │
│     → "{cause} {effect} RCT OR meta-analysis OR randomized   │
│        OR natural experiment OR causal {domain}"             │
│  3. composed_search(query) → P3 search results              │
│  4. classify_evidence(results) → CausalVerdict + citation    │
│  5. adjust_posterior(verdict) → delta applied to CALIBRATE   │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 New Files

| File | Purpose |
|---|---|
| `eif/causal_gate/evidence_probe.py` | CEP implementation: extract, search, classify |
| `eif/causal_gate/verdict.py` | CausalVerdict enum, posterior adjustment logic |

### 3.4 Modified Files

| File | Change |
|---|---|
| `eif/causal_gate/__init__.py` | Export `run_causal_evidence_probe` |
| `eif/schemas.py` | Add `CausalVerdict` enum, `CausalEvidenceResult` Pydantic model |
| `eif/record/provenance.py` | Add `CAUSAL_UNVERIFIED` provenance flag |

---

## 4. Data Structures

### 4.1 CausalVerdict Enum

```python
class CausalVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"      # RCT/meta-analysis supports causal direction
    CONTESTED = "CONTESTED"      # Evidence found, contradicts or shows null
    NO_EVIDENCE = "NO_EVIDENCE"  # No causal studies found for this relationship
    REVERSED = "REVERSED"        # Evidence supports opposite causal direction
```

### 4.2 CausalEvidenceResult Model

```python
class CausalEvidenceResult(BaseModel):
    claim_text: str
    cause: str
    effect: str
    domain: str
    causal_level: CausalLevel          # from v3
    verdict: CausalVerdict
    citation: str | None               # study title + year, or None if NO_EVIDENCE
    search_query: str                  # the P3 query used
    evidence_source: str = "P3_WEB_SEARCH"
    posterior_delta: float              # adjustment applied to CALIBRATE
    provenance_flag: str | None        # "CAUSAL_UNVERIFIED" if NO_EVIDENCE + HIGH
```

### 4.3 Posterior Adjustments

| Verdict | Delta | Rationale |
|---|---|---|
| SUPPORTED | +0.15 | Independent causal evidence found - strengthens claim |
| NO_EVIDENCE | 0.00 | Absence of evidence ≠ evidence of absence |
| CONTESTED | -0.20 | Counter-evidence or null results - weakens but doesn't disprove |
| REVERSED | -0.35 | Same magnitude as FALSIFY CONTRADICTS - strong disconfirmation |

---

## 5. Implementation: `evidence_probe.py`

### 5.1 `extract_causal_pair`

Uses a lightweight LLM prompt (gpt-4.1-mini, ~200 tokens) to extract:
- `cause`: the proposed causal variable
- `effect`: the proposed effect variable  
- `domain`: the field (healthcare, finance, engineering, etc.)

Prompt template:

```
Given this causal claim: "{claim_text}"
Extract the cause variable, effect variable, and domain.
Return JSON: {"cause": "...", "effect": "...", "domain": "..."}
```

### 5.2 `formulate_search_query`

Deterministic string construction:

```python
def formulate_search_query(cause: str, effect: str, domain: str) -> str:
    return f"{cause} {effect} RCT OR meta-analysis OR randomized OR natural experiment OR causal {domain}"
```

### 5.3 `composed_search` (existing)

Reuses `eif.falsify.native_tools.composed_search`:
1. OpenAI `web_search_preview` (if available)
2. Fallback: DDGS (always available, zero host dependency)

### 5.4 `classify_evidence`

LLM prompt (gpt-4.1-mini, ~500 tokens) classifying the P3 search results:

```
Given these search results about whether "{cause}" causally affects "{effect}":

{search_results}

Classify the causal evidence:
- SUPPORTED: RCT, meta-analysis, or natural experiment found that supports this causal direction
- CONTESTED: Evidence found but shows null effect or contradicts the direction
- NO_EVIDENCE: No causal studies (RCTs, meta-analyses) found for this specific relationship
- REVERSED: Evidence supports the opposite causal direction

Return JSON: {"verdict": "...", "citation": "study title (year)" or null}
```

### 5.5 Cost Estimate

| Component | Model | Tokens | Cost per call |
|---|---|---|---|
| extract_causal_pair | gpt-4.1-mini | ~300 | ~$0.0004 |
| composed_search (DDGS) | - | - | $0.00 |
| classify_evidence | gpt-4.1-mini | ~700 | ~$0.0009 |
| **Total per CEP** | | | **~$0.0013** |

At ~5 HIGH causal claims per 6-turn session: **~$0.007 additional cost per session**.

---

## 6. Integration with CALIBRATE

```python
# In the calibration loop, after FALSIFY evidence:
if claim.causal_evidence_result:
    posterior += claim.causal_evidence_result.posterior_delta
    # Clamp to [0.0, 1.0]
    posterior = max(0.0, min(1.0, posterior))
```

The delta stacks with FALSIFY verdicts. A claim can be:
- SUPPORTED by P3 evidence AND SUPPORTED by CEP → strong ACT signal
- CONTRADICTED by P3 evidence AND REVERSED by CEP → deep HALT

---

## 7. Integration with RECORD

When `verdict == NO_EVIDENCE` and `consequence == HIGH`:

```python
provenance_row["causal_verdict"] = "NO_EVIDENCE"
provenance_row["provenance_flag"] = "CAUSAL_UNVERIFIED"
```

This satisfies EU AI Act Art. 9: the system explicitly documents that a high-risk
causal claim could not be independently verified. Reviewers and auditors can filter
on `CAUSAL_UNVERIFIED` to identify claims requiring human causal assessment.

---

## 8. Testing Strategy

| Test | Input | Expected |
|---|---|---|
| Trigger guard: LOW claim | "latency correlates with throughput" (LOW/ASSOC) | No CEP fired |
| Trigger guard: MEDIUM claim | "caching reduces latency" (MED/INTERVENTION) | No CEP fired |
| Fire condition: HIGH/INTERVENTION | "microservices cause higher availability" (HIGH/INTERVENTION) | CEP fires, search executed |
| Known causal: smoking→cancer | "smoking causes lung cancer" (HIGH/INTERVENTION) | SUPPORTED + citation |
| Known non-causal: ice cream→drowning | "ice cream consumption causes drowning" (HIGH/INTERVENTION) | CONTESTED or NO_EVIDENCE |
| No P4 fallback | Any claim where DDGS returns results | evidence_source == P3_WEB_SEARCH |
| Citation required for SUPPORTED | Any SUPPORTED verdict | citation field is not None |
| Latency | 10 sequential CEP calls | mean < 3s |
| Provenance flag | HIGH + NO_EVIDENCE | JSONL contains CAUSAL_UNVERIFIED |

---

## 9. Research Bibliography

| Reference | ID | Relevance |
|---|---|---|
| Pearl - Causality (2009) | Cambridge UP | Ladder of Causation, do-calculus (canonical) |
| ERM - Epistemic Regret Minimization | arXiv:2602.11675 | Rung Collapse detection methodology |
| CRAwDAD - Dual-Agent Causal Debate | arXiv:2511.22854 | Multi-agent causal accuracy improvement |
| Ariadne - Structural Causal Audit | arXiv:2601.02314 | Reasoning faithfulness via hard interventions |
| ReCITE - Real-World Causal Inference | arXiv:2505.18931 | Benchmark: F1=0.535 (LLM ceiling) |
| DoVerifier - Symbolic do-calculus Verification | arXiv:2601.21210 | Symbolic verification of causal expressions |
| CausalBench - Multi-dimensional Evaluation | OpenReview 2025 | Four-perspective causal reasoning eval |
| DMCD - Semantic-Statistical Discovery | arXiv:2602.20333 | LLM+statistics hybrid DAG construction |
| DoWhy - Causal Inference Library | py-why/dowhy (8,049★) | Refutation API design reference |
| causal-learn - Causal Discovery | py-why/causal-learn (1,579★) | DAG algorithm reference |

# EIF Architecture

**Epistemic Integrity Framework (eif-engine 4.0.0): system design reference.**

---

## Overview

EIF is a development-time verification library and MCP server. It applies the scientific method's core loop (conjecture, falsification, calibration, explanation) to claims made by AI agents before those claims are acted on.

It does not replace the agent. It audits the agent's epistemic state: what the agent knows versus what it assumes, and whether independent evidence supports acting on those assumptions. The output is a routing signal (ACT, REVISE, HALT) plus a local provenance record. The caller or agent controller decides what to do with both.

EIF is source you run yourself, with everything on your infrastructure. An optional private-alpha hosted MCP endpoint also exists (`eif.leocelis.com`) as a zero-install convenience: no account system beyond a Bearer key, no billing, no telemetry. See [PRIVACY_POLICY.md](../PRIVACY_POLICY.md) for the exact data-handling difference between the two paths.

---

## Pipeline

Eight core phases, in order:

```
DECLARE          → name every assumption: KNOWN / ASSUMED / GUESSED
FALSIFY          → collect independent evidence (tiers P0..P4, SPRT orientation)
CAUSAL_GATE      → check Pearl causal level; flag confounders and direction errors
CALIBRATE        → Bayesian posterior update (prior x likelihood → route)
CHALLENGE        → adversarial critic produces counter-evidence and a competing hypothesis
UPDATE           → sequential Bayes update; EIG stopping rule
EXPLAIN          → hard-to-vary check (Deutsch): every detail must be functionally irreplaceable
RECORD           → provenance record with informational EU AI Act article mapping
```

Plus auxiliary gates that run before or after the core loop:

```
INPUT_GUARD       → detect adversarial or manipulative inputs before the pipeline runs
SYCOPHANCY_GATE   → detect position drift, unfaithful CoT, face-preserving framing
HYPOTHESIS_AGENDA → rank claims by Expected Information Gain before FALSIFY
REPLICATE         → pre-registered replication protocol for cross-session reproducibility
PROGRAMME         → Lakatos health monitor: PROGRESSIVE / STABLE / DEGENERATIVE
```

---

## Routing thresholds

Defined as constants in `eif/schemas.py`:

| Constant | Value |
|---|---|
| `THRESHOLD_ACT` | 0.70 |
| `THRESHOLD_REVISE` | 0.40 |
| `THRESHOLD_HALT` | 0.20 |

Routing of a claim's posterior:

| Posterior | Route |
|---|---|
| >= 0.70 | ACT (maintain course) |
| 0.40 to 0.70 | REVISE (return to DECLARE, gather more evidence) |
| 0.20 to 0.40 | REVISE with urgency (high uncertainty band) |
| < 0.20 | HALT (escalate to human) |

---

## Evidence tiers

FALSIFY collects evidence through a five-tier fall-through strategy (`eif/falsify/evidence_collector.py`). Runtime order: P0, then P2 before P1 (coordinator outputs are free and already collected), then P3, then P4.

| Tier | Source | Notes |
|---|---|---|
| P0 | HOST_TOOL | The host agent's registered tools. Authoritative, highest priority, checked first. |
| P1 | CODE_EXECUTION | Execute Python against real data. Strongest for numerical claims. |
| P2 | TOOL_OUTPUT | The coordinator's existing tool call results. No extra network cost. |
| P3 | WEB_SEARCH | Dedicated multi-source search per claim via DDGS (DuckDuckGo). |
| P4 | PARAMETRIC | LLM parametric probe. Fallback only, capped at INSUFFICIENT, and not fired from the `eif_verify` MCP facade. Blocked for self-generated claims (self-preference bias). |

---

## Module map

Generated from the current source tree.

```
eif/
├── schemas.py               : Pydantic v2 models and constants (thresholds live here)
├── session.py               : async in-memory session store with per-session locks
├── auto.py                  : zero-config EIF interceptor import hook
│
├── input_guard/             : INPUT_GUARD gate
│   └── detector.py          : adversarial input detection before DECLARE
│
├── declare/                 : Phase 1, DECLARE
│   ├── extractor.py         : natural-language decision to structured claims
│   ├── registry.py          : AssumptionRegistry builder
│   └── harking_guard.py     : HARKing detection (hypothesizing after results known)
│
├── hypothesis_agenda/       : HYPOTHESIS_AGENDA gate
│   ├── scorer.py            : Bayesian EIG-based priority scoring
│   ├── agenda.py            : ranked HypothesisAgenda from a registry
│   └── fdr.py               : FDR correction annotation
│
├── falsify/                 : Phase 2, FALSIFY
│   ├── evidence_collector.py: five-tier grounded evidence collection (P0..P4)
│   ├── native_tools.py      : self-sufficient P1 sandbox + P3 DDGS search client
│   ├── sprt.py              : Sequential Probability Ratio Test (POPPER orientation)
│   ├── condition.py         : FalsificationCondition builder
│   ├── hard_to_vary.py      : Deutsch criterion for falsification conditions
│   └── trivial_check.py     : detect trivially satisfiable conditions
│
├── causal_gate/             : CAUSAL_GATE phase
│   ├── intervention.py      : Pearl causal level classification
│   ├── confound.py          : confounder detection
│   ├── direction.py         : causal direction check
│   ├── evidence_probe.py    : Causal Evidence Probe (optional OpenAI-backed)
│   ├── verdict.py           : posterior adjustment from the causal verdict
│   └── iris_pipeline.py     : IRIS iterative causal discovery pipeline
│
├── calibrate/               : Phase 3, CALIBRATE
│   ├── bayesian.py          : posterior computation P(H|E)
│   ├── trust.py             : tier- and confidence-aware likelihood weighting
│   ├── prior_strategy.py    : prior strategy selection
│   ├── domain_constraints.py: domain-specific posterior ceiling table
│   ├── conformal.py         : conformal prediction coverage
│   └── ece.py               : Expected Calibration Error
│
├── challenge/               : Phase 4, CHALLENGE
│   ├── protocol.py          : challenge protocol generation
│   ├── multi_critic.py      : multi-critic adversarial LLM calls (optional)
│   ├── diversity.py         : critic independence classification
│   └── replicator.py        : adversarial replicator agent
│
├── sycophancy/              : SYCOPHANCY_GATE
│   ├── detector.py          : orchestrates the S1..S4 detectors
│   ├── framing.py           : agreement-before-evidence, framing detection
│   ├── drift.py             : position drift + PositionRegister
│   ├── faithfulness.py      : unfaithful CoT detection
│   └── cost_model.py        : maps sycophancy signals to cost estimates
│
├── update/                  : Phase 5, UPDATE
│   ├── posterior.py         : sequential Bayesian posterior update
│   ├── eig.py               : Expected Information Gain computation
│   ├── stopping.py          : stopping rule evaluation
│   └── paradigm.py          : paradigm-level revision detector
│
├── explain/                 : Phase 5.5, EXPLAIN
│   ├── hard_to_vary.py      : hard-to-vary check for explanations
│   ├── artifact.py          : ExplanationArtifact builder
│   └── reach.py             : explanation reach classification (LOCAL vs BROADER)
│
├── record/                  : Phase 6, RECORD
│   ├── provenance.py        : ProvenanceRecord assembly
│   ├── chain.py             : append records to the session provenance chain
│   ├── compliance.py        : informational EU AI Act article mapping
│   ├── outcome_store.py     : cross-session outcome persistence
│   ├── isc_disclosure.py    : ISC AI disclosure taxonomy
│   └── research_object.py   : research object + DeepTRACE 8-dimension audit
│
├── replicate/               : Phase 7, REPLICATE
│   ├── protocol.py          : replication protocol generation
│   ├── divergence.py        : replication agreement rate
│   └── independent.py       : independent convergent replication
│
├── programme/               : Phase 8, PROGRAMME
│   ├── signals.py           : ProgrammeSignals from the provenance chain
│   ├── monitor.py           : PROGRESSIVE / STABLE / DEGENERATIVE status
│   ├── status.py            : human-readable status text
│   ├── principle_memory.py  : persistent principle space memory
│   └── principle_revision.py: principle-level revision
│
├── cost_model/
│   ├── cost_ledger.py       : cumulative cost-protected ledger (~/.eif/cost_ledger.json)
│   └── catch_rate_empirical.py : empirical catch-rate measurement
│
├── memory/
│   └── strategy.py          : cross-session strategic memory
│
├── integration/             : Python-native EIF without MCP
│   ├── eif_auto.py          : generic EIF guard for any Python agent
│   └── interceptor.py       : LangChain callback handler
│
├── sdk/                     : local interceptor surfaces for in-code agents
│   ├── interceptor.py       : SDK interceptor
│   └── exceptions.py        : HALT verdicts surfaced as exceptions
│
├── reporting/
│   └── pdf_renderer.py      : compliance report PDF renderer
│
└── mcp_server/
    ├── server.py            : FastMCP server, 25 tools + 5 resources
    ├── resources.py         : MCP resource handler implementations
    ├── http_server.py       : optional self-hosted HTTP/SSE server
    └── auth.py              : optional single-key auth (EIF_API_KEY)
```

---

## MCP surface

`eif/mcp_server/server.py` exposes 25 tools and 5 resources.

**Tools.** `eif_new_session` creates the session every other stateful tool requires. One tool per pipeline phase and gate (`eif_declare`, `eif_falsify`, `eif_causal_gate`, `eif_calibrate`, `eif_challenge`, `eif_update`, `eif_explain`, `eif_record`, `eif_replicate`, `eif_input_guard`, `eif_sycophancy_gate`, `eif_hypothesis_agenda`, `eif_programme_health`), plus the one-call facade `eif_verify` (runs the full pipeline over a decision, P0 through P3, no P4), and utility tools (`eif_get_context`, `eif_extract_claims_from_decision`, `eif_provenance`, `eif_check_rules_installed`, `eif_get_session`, `eif_compliance_report`, `eif_record_outcome`, `eif_calibration_report`, `eif_catch_rate_report`, `eif_demo`).

**Resources.** Five per-session read surfaces: `eif://session/{id}/summary`, `/registry`, `/provenance`, `/programme`, `/calibration`.

**Transports.**

- stdio: `eif-mcp-server`, the default for local MCP clients.
- Optional local HTTP/SSE: `eif-mcp-http-server`, bound to 127.0.0.1 by default, with optional single-key auth via `EIF_API_KEY` (no key set means open dev mode locally).
- Docker image built from this repository.
- Optional hosted alpha: the maintainer runs the same HTTP/SSE server at `eif.leocelis.com` (Bearer key required, private alpha). See the README's MCP server section.

---

## Design principles

1. **No LLM calls in the core engine.** The engine is zero-LLM and zero-network; all evidence collection lives in the integration layer. `llm_fn` and `search_fn` hooks are injectable, caller-supplied, and default to None or to deterministic heuristics. Optional outbound calls exist only at the edges: DDGS web search for P3, and OpenAI calls for the CHALLENGE multi-critic and the causal evidence probe, only if the user sets `OPENAI_API_KEY`.

2. **Deterministic math.** Posteriors, SPRT, EIG, ECE, and routing are computed with plain deterministic formulas over Pydantic v2 models (`eif/schemas.py`). Same inputs, same route.

3. **No circular validation.** Evidence for a claim must come from a source independent of the LLM that generated the claim. P4 is last resort, capped, and blocked for self-generated claims.

4. **Session-level reasoning.** A claim HALT-routed in turn N is flagged if the position softens later without new evidence. Per-claim accuracy is not enough; the position across turns matters.

5. **Adversarial by design.** CHALLENGE uses an independent critic tasked to find the strongest counter-evidence. Agreement between agent and critic is a sycophancy signal, not validation.

6. **Local and auditable.** Every probe, posterior update, routing decision, and gate event is written to local JSONL under `~/.eif/`. Nothing leaves your machine except the optional P3 search queries and optional OpenAI calls described above.

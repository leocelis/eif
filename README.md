<p align="center">
  <strong>EIF - Epistemic Integrity Framework</strong><br>
  <em>Apply the scientific method to every assumption your AI agent makes.</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-compatible-purple.svg" alt="MCP Compatible"></a>
  <a href="https://github.com/leocelis/eif/actions/workflows/ci.yml"><img src="https://github.com/leocelis/eif/actions/workflows/ci.yml/badge.svg" alt="tests"></a>
  <a href="https://trust.complyedge.io/eif"><img src="https://api.complyedge.io/v1/public/badge/eif.svg" alt="ComplyEdge runtime enforcement"></a>
</p>

---

## The problem

AI agents compound errors. Each assumption that goes unchallenged becomes the foundation for the next one. A 90%-accurate agent running 10-step tasks produces correct output only 35% of the time - that's the compound error curve. That `0.9^10` curve is an upper bound: it assumes independent, non-recoverable per-step errors, whereas real pipelines have correlated and recoverable steps, so EIF's value is framed as reducing the error rate per load-bearing step rather than as the literal compound figure. In high-stakes domains (compliance, engineering decisions, financial advice), this translates to real cost.

The dominant source of that cost is not hallucinated facts, but unchallenged assumptions that are never tested against evidence.

---

## What EIF does

EIF is a Python library and MCP server that runs an 8-phase scientific-method pipeline on every load-bearing assumption in an agent's response:

```
DECLARE          → name every assumption: KNOWN / ASSUMED / GUESSED
FALSIFY          → collect independent evidence via P1 code, P2 tools, P3 web search
CAUSAL_GATE      → check Pearl causal level; flag confounders and disjunctive bias
CALIBRATE        → Bayesian posterior update (prior × likelihood → route)
CHALLENGE        → adversarial critic produces counter-evidence and competing hypothesis
UPDATE           → sequential Bayes update; EIG stopping rule
EXPLAIN          → hard-to-vary check (Deutsch): every detail must be functionally irreplaceable
RECORD           → provenance record with EU AI Act compliance mapping
```

Plus auxiliary gates that run before/after the core loop:

```
INPUT_GUARD      → detect adversarial or manipulative inputs before the pipeline runs
SYCOPHANCY_GATE  → detect position drift, unfaithful CoT, and face-preserving framing
HYPOTHESIS_AGENDA → rank claims by Expected Information Gain before FALSIFY
REPLICATE        → pre-registered replication protocol for cross-session reproducibility
PROGRAMME        → Lakatos health monitor: PROGRESSIVE / STABLE / DEGENERATIVE
```

At the end of each turn, EIF routes the agent's output:
- **ACT** - posterior ≥ threshold, evidence supports, safe to proceed
- **REVISE** - some assumptions unresolved, moderate confidence
- **HALT** - evidence contradicts a HIGH-consequence claim; do not proceed

---

## Corpus evidence

EIF was validated against **14 multi-agent conversation scenarios** across 5 domains (clinical, engineering, compliance, investment, M&A).

> **Scope note:** the 14-scenario corpus is constructed and illustrative - it demonstrates the mechanisms, not field results. A separate field-validation track on real agent traffic is the basis for production false-positive measurement. EIF can also estimate a modeled dollar cost per HALT-routed claim (a distinct feature); those figures and their methodology live in [`validation/CORPUS_REPORT.md`](validation/CORPUS_REPORT.md), not here.

| Scenario | Domain | Turns | HALT | REVISE | ACT |
|---------|--------|-------|------|--------|-----|
| S8v31 ML Model Deployment (FDA SaMD) | clinical | 6 | **6** | 0 | 0 |
| S7v31 Code Review / API Security | engineering | 6 | **5** | 1 | 0 |
| S6v31 Investment Decision - Series A | investment | 6 | **5** | 1 | 0 |
| S10 Sycophancy Validation | investment | 6 | **5** | 1 | 0 |
| S11 Sycophancy Market Gap | investment | 9 | **4** | 2 | 0 |
| S20 Sycophancy Full-Signal | compliance | 6 | **4** | 0 | 2 |
| S18 Reasoning Theater | compliance | 6 | **2** | 1 | 3 |
| S19b Model Scaling Ablation (gpt-4o) | investment | 6 | **2** | 3 | 1 |
| S16 REVERSED CEP - Beta-carotene/CARET | clinical | 3 | **1** | 2 | 0 |
| S15 CAUSAL_GATE v4 - Phase 3 Protocol | clinical | 6 | **1** | 1 | 4 |
| S9v31 M&A Due Diligence | manda | 6 | 0 | 4 | 2 |
| S14 EXPLAIN Cold-Start Baseline | engineering | 6 | 0 | 0 | 0 |
| S17 Disjunctive Bias - clinical supplements | clinical | 6 | 0 | 4 | 2 |
| S19a Model Scaling Ablation (gpt-4o-mini) | investment | 6 | 0 | 5 | 1 |
| **TOTAL** | | **84** | **35** | **25** | **15** |

**P4 (circular LLM self-validation) rate: 0.0% across all 14 scenarios.** Every piece of evidence came from an independent source - executable code, coordinator tool outputs, or live web search.

Full evidence: [`validation/CORPUS_REPORT.md`](validation/CORPUS_REPORT.md). Per-scenario reports available on request via GitHub Discussions.

---

## Quick start

```bash
pip install -e ".[mcp]"   # local dev (the MCP extra powers the examples below)
# or: uvx --from eif-engine eif-mcp-server   # zero-install stdio MCP server
```

### Two-tool path (recommended for first session)

```python
import asyncio
from eif import session as session_store
from eif.mcp_server.server import eif_extract_claims_from_decision, eif_verify

async def run():
    sess = await session_store.new_session()
    sid = sess.session_id

    # Step 1: Describe the agent's decision in plain English.
    # EIF extracts 2-4 load-bearing claims automatically (no JSON required).
    extracted = eif_extract_claims_from_decision(
        "Commission a 10-article series on Hollow Ascent. "
        "The game has 5,000+ IGDB hype followers and strong community demand."
    )

    # Step 2: Run the full pipeline - declare, falsify, calibrate, route.
    # If a claim is HALT-routed, halt_cards shows the blocked claim + evidence.
    result = await eif_verify(
        session_id=sid,
        decision="Commission content series based on IGDB metrics",
        claims=extracted["claims"],
    )

    print(f"Verdict: {result['verdict']}")  # "HALT" or "PASS"
    for card in result["halt_cards"]:
        print(card)

asyncio.run(run())
```

### Register a P0 host tool (highest-accuracy evidence tier)

When your agent has access to an authoritative data source (IGDB, your database, an internal API), register it as a P0 host tool. EIF calls it directly - no web search, no guessing.

```python
from eif.falsify.evidence_collector import HostTool, HostToolRegistry

# One function: takes a query string, returns the raw data as a string.
def igdb_lookup(query: str) -> str:
    import requests
    resp = requests.get("https://api.igdb.com/v4/games", ...)  # your IGDB call
    return str(resp.json())

registry = HostToolRegistry([
    HostTool(
        name="igdb_api",
        description="IGDB game database - hype count, ratings, community size",
        capability_keywords=["igdb", "hype", "game", "demand", "followers"],
        fn=igdb_lookup,
        data_scope="PUBLIC",
    )
])

# Pass the registry to eif_verify via host_tool_outputs (MCP path)
# or directly to collect_evidence() in the Python integration layer.
```

P0 is the highest-priority evidence tier. Without a registered tool, EIF falls back to web search (P3), which can return false-positive SUPPORTS for specific numeric metrics. For production use, **register the tool**.

See [`examples/quickstart.py`](examples/quickstart.py) for a complete end-to-end example (a different scenario, an infrastructure-migration decision, walking DECLARE through EXPLAIN in one script).

---

## MCP server (Cursor / Claude Code / Claude Desktop integration)

Per-client setup guides (register the server, install the rules block, verify,
troubleshoot) live in [`docs/integrations/`](docs/integrations/README.md):
[Claude Code](docs/integrations/CLAUDE_CODE.md) ·
[Cursor](docs/integrations/CURSOR.md) ·
[Claude Desktop](docs/integrations/CLAUDE_DESKTOP.md).
The short version:

**Option A - hosted endpoint (private alpha, zero install):**

Request a key by [opening a Discussion](https://github.com/leocelis/eif/discussions), then add the config for your client.

Cursor (`~/.cursor/mcp.json`) and Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "eif": {
      "url": "https://eif.leocelis.com/sse",
      "headers": { "Authorization": "Bearer YOUR_KEY_HERE" }
    }
  }
}
```

VS Code / GitHub Copilot (`.vscode/mcp.json`): use `"servers"` (not `"mcpServers"`) and add `"type": "http"` to the entry.

> The hosted endpoint is in private alpha. Everything below runs fully on your own machine with no key.

**Option B - local venv (works today, fully self-hosted):**

```json
{
  "mcpServers": {
    "eif": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "eif.mcp_server.server"]
    }
  }
}
```

**Option C - uvx (zero-install, works today):**

```json
{
  "mcpServers": {
    "eif": {
      "command": "uvx",
      "args": ["--from", "eif-engine", "eif-mcp-server"]
    }
  }
}
```

`uv` runs the executable matching the package name by default; since the console
scripts are `eif-mcp-server` / `eif-mcp-http-server` (not `eif-engine`), `--from`
is required. Bare `uvx eif-engine` fails with "An executable named `eif-engine`
is not provided by package `eif-engine`".

EIF exposes **25 tools** your agent can call:

**Session (1 tool):**

| Tool | What it does |
|------|-------------|
| `eif_new_session` | Create a session; every other tool requires its session_id |

**Core pipeline (8 tools):**

| Tool | Phase | What it does |
|------|-------|-------------|
| `eif_get_context` | - | Load EIF principles into agent context |
| `eif_declare` | DECLARE | Register and classify every assumption |
| `eif_falsify` | FALSIFY | Collect independent evidence; run SPRT |
| `eif_causal_gate` | CAUSAL_GATE | Check Pearl causal level; flag confounders |
| `eif_calibrate` | CALIBRATE | Bayesian posterior; compute routing |
| `eif_challenge` | CHALLENGE | Adversarial critic with counter-evidence |
| `eif_update` | UPDATE | Sequential posterior update; EIG stopping |
| `eif_explain` | EXPLAIN | Hard-to-vary check on the mechanism |

**Gates and monitors (5 tools):**

| Tool | What it does |
|------|-------------|
| `eif_input_guard` | Detect adversarial or manipulative inputs |
| `eif_sycophancy_gate` | Detect position drift, unfaithful CoT, face-preserving framing |
| `eif_programme_health` | Lakatos health monitor for the session |
| `eif_record` | Write provenance record; EU AI Act compliance mapping |
| `eif_replicate` | Pre-registered replication protocol |

**Calibration and agenda (4 tools):**

| Tool | What it does |
|------|-------------|
| `eif_record_outcome` | Log a session's labeled outcome (true/false) for cross-session ECE calibration |
| `eif_calibration_report` | Return ECE state, empirical prior, and sessions-to-grounded count |
| `eif_catch_rate_report` | Empirical HALT catch-rate across all sessions for a domain |
| `eif_hypothesis_agenda` | Rank outstanding hypotheses by Expected Information Gain before FALSIFY |

**Utilities (7 tools):**

| Tool | What it does |
|------|-------------|
| `eif_verify` | One-call full pipeline: declare → falsify → calibrate → route |
| `eif_extract_claims_from_decision` | Extract structured claims from free-form agent text |
| `eif_compliance_report` | Generate EU AI Act compliance report for a session |
| `eif_provenance` | Retrieve the full provenance chain for a session |
| `eif_get_session` | Inspect current session state |
| `eif_demo` | Zero-setup HALT example (Manor Lords / IGDB) |
| `eif_check_rules_installed` | Verify the EIF agent-rules block (see below) is installed in your instruction files |

**Recommended agent loop** (in your system prompt or MCP server instructions):

```
1. eif_new_session              - once per decision or task; store the session_id
2. eif_get_context              - once per session (granular pipeline only)
3. eif_input_guard              - before processing any user input
4. eif_declare                  - after every response with load-bearing claims
5. eif_falsify                  - for ASSUMED/GUESSED HIGH-consequence claims
6. eif_causal_gate              - if any claim asserts X causes Y
7. eif_calibrate                - route: ACT / REVISE / HALT
8. eif_challenge + eif_update   - when routing is REVISE or HALT
9. eif_sycophancy_gate          - if the agent changed position under pressure
10. eif_explain                 - before sharing final recommendation
11. eif_record                  - write the provenance record
```

Paste the block below into an agent instruction file (`.cursorrules`, `CLAUDE.md`,
`AGENTS.md`, or `.cursor/rules/eif.mdc`) so `eif_check_rules_installed` can confirm
it is present and your agent picks up the loop automatically:

```
# <BEGIN-EIF v1.3>
# ==============================================================================
# EIF - Epistemic Integrity Framework
# ==============================================================================
# Reference: https://github.com/leocelis/eif
#
# EIF applies the scientific method to load-bearing claims before you act on
# them. Use it on decisions where being confidently wrong is costly: financial
# moves, irreversible actions, compliance or engineering calls, anything you
# would defend with a number or a causal claim.
#
# What eif_verify catches that a naive hallucination check misses:
#   - sycophantic drift: the answer changed under user pressure, not evidence
#   - self-preference bias: the model trusting its own prior output
#   - correlation presented as causation
#   - stochastic fabrication: the same claim returns different numbers when
#     re-checked (instability_signals in the response flags this)
#
# Recommended loop:
#   1. eif_new_session once per decision or task; store the session_id it
#      returns and pass THAT to every other tool. Never invent a session_id;
#      an unknown id fails with "session not found".
#   2. Before ACTING on a decision with load-bearing factual or causal claims:
#      eif_verify(session_id, decision, claims). Prefer
#      eif_extract_claims_from_decision to build the claims - it sets the
#      fields correctly. If you hand-write a claim, claim_type must be exactly
#      KNOWN, ASSUMED, or GUESSED; no other value validates.
#   3. Pass data you ALREADY fetched (DB rows, API results, tool output) as
#      host_tool_outputs. That is P0 evidence, the highest tier, and it is what
#      lets EIF check a number against ground truth instead of guessing.
#   4. Verdict HALT: do not act; surface halt_cards to the user. REVISE:
#      gather more evidence before acting. PASS: proceed.
#   5. Re-verify after the user pushes back across turns: sycophantic drift is
#      otherwise invisible.
#
# eif_get_context (once per session) is only needed for the granular pipeline
# (eif_declare -> eif_falsify -> ...), not for the eif_verify path above.
#
# Do NOT run eif_verify on every reply. Reserve it for consequential decisions;
# routine chatter does not need it.
# <END-EIF v1.3>
```

The canonical text of this block lives in
[`docs/integrations/README.md`](docs/integrations/README.md); the checker
accepts any `<BEGIN-EIF vX.Y>` marker, so existing v1.0 installs stay valid.

---

## Evidence collection tiers

EIF's `FALSIFY` phase collects evidence from independent sources, prioritised:

| Tier | Trigger | Source |
|------|---------|--------|
| **P0** HOST_TOOL | Host agent has a registered tool for this data source | Calls the authoritative data API directly (e.g. IGDB, EHR, internal DB) |
| **P1** CODE_EXECUTION | Numerical/metric claims | Executes Python against public benchmark data |
| **P2** TOOL_OUTPUT | Agent tool calls available | Parses coordinator web search / API results |
| **P3** WEB_SEARCH | Regulatory / temporal claims | Live web search via DDGS native or OpenAI responses API |
| **P4** PARAMETRIC | All else (capped) | LLM parametric probe - fallback only |

P0 is the highest-priority tier and is the mechanism used in the Manor Lords / IGDB demo. P4 is never used for company-specific claims. In the validation corpus, P4 rate was **0.0%** across all 14 scenarios.

---

## Architecture

```
eif/
├── schemas.py                  Pydantic v2 models (dependency root)
├── session.py                  Async in-memory session store
├── declare/
│   ├── registry.py             Assumption registry + KNOWN/ASSUMED/GUESSED classifier
│   └── harking_guard.py        HARKing detection (Hypothesizing After Results are Known)
├── falsify/
│   ├── evidence_collector.py   Five-tier evidence collection (P0–P4)
│   ├── native_tools.py         Self-sufficient P1+P3 tools (DDGS + code sandbox)
│   ├── sprt.py                 Sequential Probability Ratio Test
│   ├── condition.py            Falsification condition parser
│   ├── hard_to_vary.py         Deutsch criterion applied to falsification conditions
│   └── trivial_check.py        Detect trivially satisfiable conditions
├── causal_gate/
│   ├── intervention.py         Pearl causal levels (L1/L2/L3) + intervention check
│   ├── confound.py             Confounder and disjunctive bias detection
│   ├── direction.py            Temporal direction heuristic
│   ├── evidence_probe.py       Causal Evidence Probe (CEP) - v4
│   └── verdict.py              CausalVerdict → posterior adjustment
├── calibrate/
│   ├── bayesian.py             Bayesian posterior: P(H|E) = P(E|H)×P(H) / P(E)
│   ├── ece.py                  Expected Calibration Error
│   ├── conformal.py            Conformal prediction coverage
│   └── prior_strategy.py       Prior auto-selection (max_entropy / empirical_bayes / domain)
├── hypothesis_agenda/
│   ├── scorer.py               EIG × consequence × boundary × uncertainty priority score
│   └── agenda.py               Build ranked HypothesisAgenda from AssumptionRegistry
├── challenge/
│   ├── protocol.py             Adversarial critic protocol builder
│   ├── multi_critic.py         Multi-critic with actual LLM calls + independence check
│   └── diversity.py            Critic independence classifier
├── update/
│   ├── posterior.py            Sequential Bayesian posterior update
│   ├── eig.py                  Expected Information Gain (KL divergence)
│   └── stopping.py             EIG / SPRT / cost stopping rules
├── explain/
│   ├── hard_to_vary.py         Deutsch hard-to-vary check + domain-specificity anchor gate
│   ├── artifact.py             ExplanationArtifact builder
│   └── reach.py                LOCAL vs BROADER scope classifier
├── sycophancy/
│   ├── detector.py             Orchestrates M1–M4 sycophancy detectors
│   ├── drift.py                M2: Position drift detector
│   ├── faithfulness.py         M3: Unfaithful CoT detector
│   ├── framing.py              M1/M4: Agreement-before-evidence + face-preserving framing
│   └── cost_model.py           Domain-specific dollar cost model for sycophancy events
├── input_guard/
│   └── detector.py             Adversarial input detection (D1–D5)
├── record/
│   ├── provenance.py           Build ProvenanceRecord from session state
│   ├── compliance.py           Map ProvenanceRecord → EU AI Act articles
│   └── chain.py                Append record to session provenance chain
├── replicate/
│   ├── protocol.py             Pre-registered replication protocol generator
│   └── divergence.py           Evaluate replication results; compute agreement rate
├── programme/
│   ├── signals.py              Compute ProgrammeSignals from provenance chain
│   ├── monitor.py              PROGRESSIVE / STABLE / DEGENERATIVE classifier
│   └── status.py               Human-readable status + recommendation
├── cost_model/
│   ├── cost_ledger.py          Cumulative modeled-savings ledger (~/.eif/)
│   └── catch_rate_empirical.py Empirical HALT catch-rate across sessions
├── integration/
│   ├── interceptor.py          In-process LangChain callback handler (EIFCallbackHandler)
│   └── eif_auto.py             Generic guard decorator/context manager (eif_guard)
├── sdk/
│   ├── interceptor.py          EIFInterceptor (OpenAI client wrapper) + EIFCallbackHandler (LangChain/HTTP)
│   ├── exceptions.py           EIFHaltError + HaltRecord - raised when verdict = HALT
│   └── __init__.py             Public exports: EIFInterceptor, EIFCallbackHandler, EIFHaltError
├── auto.py                     Zero-config import hook (import eif.auto → intercepts all OpenAI + Anthropic)
├── reporting/
│   └── pdf_renderer.py         PDF compliance report via fpdf2
└── mcp_server/
    ├── server.py               FastMCP server - 25 tools + 5 resources (stdio)
    ├── http_server.py          HTTP/SSE transport (self-hosted)
    ├── auth.py                 Optional API key authentication (single shared key)
    └── resources.py            MCP resources (context, corpus, schema, compliance)

research/
├── foundations/                Scientific method history, philosophy, and statistics (7 files)
├── ai_agents/                  AI agent research - hypothesis generation, causal reasoning,
│                               calibration, multi-agent review, provenance (6 files)
└── sycophancy_bias_research.md Canonical sycophancy literature review
```

---

## Research foundation

EIF integrates findings from:

| Paper | Contribution |
|-------|-------------|
| Popper (1959) *Logic of Scientific Discovery* | Falsifiability as the demarcation criterion |
| Deutsch (2011) *Beginning of Infinity* | Hard-to-vary explanations as quality signal |
| Pearl (2009) *Causality* | Causal ladder L1/L2/L3 for intervention claims |
| Wald (1945) SPRT | Sequential hypothesis testing for streaming evidence |
| Sharma et al. (2023) arXiv:2310.13548 | Sycophancy in LLMs - larger models are more sycophantic |
| Truth Decay arXiv:2503.11656 (2025) | Multi-turn position erosion: ~12–18% confidence drop per pushback turn |
| ELEPHANT arXiv:2505.13995 (2025) | Five face-preserving behaviours in LLM responses |
| ERM arXiv:2602.11675 (2025) | LLMs substitute P(Y\|X) for P(Y\|do(X)) - causal rung collapse |
| IFScale (2025) | 68% accuracy at high constraint density - segmented implementation required |
| FActScore (Min et al., 2023) | Atomic claim decomposition and verification |

Full research citations: [`docs/research_foundation.md`](docs/research_foundation.md)

Primary-source literature reviews (15 documents, ~3,800 lines): [`research/`](research/README.md)

---

## Production Integration

Three surfaces for intercepting LLM responses in your code - all run locally (your responses never leave your machine).

### A) EIFInterceptor - wrap an existing OpenAI client

```python
from openai import OpenAI
from eif.sdk import EIFInterceptor, EIFHaltError

client = OpenAI()
eif = EIFInterceptor(api_key="eif-...", client=client)

try:
    response = eif.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Evaluate this plan: ..."}],
    )
    print(response.choices[0].message.content)
except EIFHaltError as e:
    print("HALT:", e.halt_record)
    # Do not act on this response - EIF found a claim without independent evidence.
```

Install: `pip install "eif-engine[sdk]"` (or `pip install -e ".[sdk]"` from a source checkout)

Note: on any EIF server error the SDK fails open (the response passes through unverified) so your agent never blocks on EIF availability. Treat `EIFHaltError` as the only enforcement signal.

### B) eif.auto - zero-config import hook

```python
import eif.auto  # add once at your agent's entry point

# All subsequent OpenAI and Anthropic calls are intercepted automatically.
# EIFHaltError is raised if a HALT verdict is reached.
```

Configure via environment:

```bash
export EIF_API_KEY="eif-..."
export EIF_SERVER_URL="http://localhost:8080"   # default
export EIF_HALT_MODE="raise"                    # raise | log | callback
```

Start the HTTP server: `eif-mcp-http-server`

### C) EIFCallbackHandler - LangChain / LangGraph

```python
from langchain.agents import AgentExecutor
from eif.sdk import EIFCallbackHandler, EIFHaltError

handler = EIFCallbackHandler(api_key="eif-...")
agent = AgentExecutor(agent=agent, tools=tools, callbacks=[handler])

try:
    result = agent.invoke({"input": task})
except EIFHaltError as e:
    print("HALT:", e.halt_record)
```

For in-process LangChain integration (no HTTP server required), use the original integration layer:

```python
from eif.integration import EIFInterceptor, EIFHaltError
interceptor = EIFInterceptor(session_id="my-session")
chain = my_chain.with_config(callbacks=[interceptor])
```

---

## Design principles

1. **No LLM calls in the engine** - all computation is deterministic local math; LLM calls happen only in evidence collection (P3/P4) and claim extraction (integration layer)
2. **Pydantic v2 throughout** - every input and output is a typed, validated model
3. **H₀ = claim-is-TRUE** - Popper orientation: REJECT means the claim fails
4. **EIG stopping rule** - stop gathering evidence when KL(posterior ∥ prior) < 0.01 nats
5. **IMP4 direction law** - `CONTRADICTS` evidence must use low `P(E|H)`, not the same likelihood as `SUPPORTS`
6. **P4 = 0% target** - parametric self-validation is never used for company-specific or causal claims

---

## Validation corpus

Full corpus: [`validation/`](validation/)

| File | Description |
|------|-------------|
| [`CORPUS_REPORT.md`](validation/CORPUS_REPORT.md) | Aggregated results across 14 scenarios, 84 agent turns |
| [`EIF_INVESTMENT_V31_EVIDENCE.md`](validation/EIF_INVESTMENT_V31_EVIDENCE.md) | Sample: Investment decision - Series A, 6 turns |
| [`aggregate_corpus.py`](validation/aggregate_corpus.py) | Aggregator script - regenerates `CORPUS_REPORT.md` |

Additional per-scenario evidence reports (S6v31–S20) available on request via GitHub Discussions.

---

## Development

```bash
git clone https://github.com/leocelis/eif && cd eif
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,mcp]"
pytest -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the repo layout, code style, and PR checklist.
CI runs the test suite (Python 3.11 and 3.12) plus a [TrustLint](https://github.com/ComplyEdge/complyedge) EU AI Act screen over the intent artifacts (`./scripts/compliance/check.sh`). See [docs/integrations/COMPLYEDGE.md](docs/integrations/COMPLYEDGE.md) for the full setup and the live trust surface.

---

## Community

- Bugs: [GitHub Issues](https://github.com/leocelis/eif/issues)
- Questions and ideas: [GitHub Discussions](https://github.com/leocelis/eif/discussions)
- Security reports: see [SECURITY.md](SECURITY.md)

---

## Legal

| Document | Covers |
|---|---|
| [LICENSE](LICENSE) | MIT license for the code |
| [LEGAL.md](LEGAL.md) | What EIF is and is not, performance-claim scope, limitations, deployer obligations |
| [TERMS_OF_SERVICE.md](TERMS_OF_SERVICE.md) | Use of the repository, docs, and project site |
| [PRIVACY_POLICY.md](PRIVACY_POLICY.md) | No telemetry; categorical no-collection when self-hosted; what the optional hosted alpha does with your claim text |
| [DATA_PROCESSING_AGREEMENT.md](DATA_PROCESSING_AGREEMENT.md) | Template (not in force) for internal enterprise deployments |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting |
| [NOTICE](NOTICE) | Third-party attributions |

Performance and market figures in this README are modeled or third-party estimates, not measured production results: see [LEGAL.md](LEGAL.md).

---

## License

MIT - see [LICENSE](LICENSE). Maintained by [Leo Celis](https://github.com/leocelis).

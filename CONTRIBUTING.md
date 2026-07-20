# Contributing to EIF

Thanks for your interest in contributing to the Epistemic Integrity Framework.

---

## Repository layout

```
eif/
├── eif/                    # Library source (installable package: eif-engine)
│   ├── declare/            #   Phase 1: assumption declaration (KNOWN/ASSUMED/GUESSED)
│   ├── falsify/            #   Phase 2: evidence collection (P1 code, P2 tools, P3 web search)
│   ├── causal_gate/        #   Phase 3: Pearl causal-level checks
│   ├── calibrate/          #   Phase 4: Bayesian posterior update and routing
│   ├── challenge/          #   Phase 5: adversarial critic
│   ├── update/             #   Phase 6: sequential Bayes update, EIG stopping rule
│   ├── explain/            #   Phase 7: hard-to-vary check
│   ├── record/             #   Phase 8: provenance records
│   ├── input_guard/        #   auxiliary gate: adversarial input detection
│   ├── sycophancy/         #   auxiliary gate: position drift detection
│   ├── hypothesis_agenda/  #   auxiliary: EIG-ranked claim agenda
│   ├── replicate/          #   auxiliary: replication protocol
│   ├── programme/          #   auxiliary: Lakatos programme health monitor
│   ├── mcp_server/         #   stdio + local HTTP MCP servers (24 tools)
│   └── sdk/                #   client-side interceptors
├── tests/                  # pytest suite (unit + integration)
├── examples/               # runnable quickstart
├── docs/                   # architecture, tech specs, research foundation
├── validation/             # validation corpus report and aggregation
├── pyproject.toml
└── README.md
```

---

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,mcp]"
```

Requires Python 3.11 or newer.

---

## Running tests

```bash
# Full suite
pytest

# Unit tests only
pytest tests/unit

# Integration tests only
pytest tests/integration
```

Async tests run automatically (`asyncio_mode = auto` in `pyproject.toml`). The suite needs no network access and no API keys.

---

## Code style

- **No LLM calls in the engine.** This is EIF's design principle #1. The core pipeline (declare, falsify math, causal gate, calibrate, update, explain, record) is deterministic and makes no outbound network calls. LLM-backed helpers (the critic tournament in CHALLENGE, the causal evidence probe) are optional, key-gated, and isolated from the core.
- Type hints on all public APIs.
- Intent artifacts (`*_intent.yaml`) live next to the code they govern. Read the relevant intent before modifying a module; update it when behavior changes.
- Keep new dependencies out of the core. Optional features go behind extras in `pyproject.toml`.

---

## Pull request checklist

- [ ] Tests added or updated for the change
- [ ] `pytest` passes locally
- [ ] README and docs updated where applicable
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] No LLM calls or outbound network calls added to the core engine

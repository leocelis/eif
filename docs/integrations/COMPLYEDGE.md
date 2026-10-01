# ComplyEdge TrustLint - EIF integration

EIF uses [ComplyEdge](https://complyedge.io) TrustLint on LLM-facing artifacts: offline EU AI Act screening, optional runtime checks, and a public trust surface.

**Tenant slug:** `eif`

---

## What runs where

| Layer | Mechanism | API key in repo? | Blocks merge? |
|-------|-----------|------------------|---------------|
| **Offline gate** | `trustlint check` via `./scripts/compliance/check.sh` | No | Yes (CI `compliance` job) |
| **Runtime enforcement (CI)** | `POST /v1/check` via `./scripts/compliance/runtime_check.sh` | No (BYOK env only) | No (opt-in, push-to-main) |
| **Runtime enforcement (MCP + `/verify`)** | `POST /v1/check` on every tool call and every `/verify` request | No (server env only) | Blocks the call itself |
| **Public proof** | Live seal + trust JSON | No | N/A |

```
edit eif/**/*_intent.yaml -> check.sh -> CI green
                    v optional BYOK
              runtime_check.sh -> /v1/check -> audit trail -> badge + trust page
```

---

## MCP server and `/verify`

With `COMPLYEDGE_API_KEY` set on the server, `eif/mcp_server/compliance.py` checks
every call twice through `POST /v1/check`:

1. the input, `direction: "prompt"`, before EIF runs it (tool name plus JSON
   arguments, or the `/verify` claim text)
2. the result, `direction: "output"`, before it is returned

All 25 tools pass through one dispatch, `ComplianceFastMCP.call_tool`, so every tool,
including future ones, is covered. A blocked check replaces the answer:

- MCP tools return `{"blocked": true, "blocked_by": "ComplyEdge", "stage", "message",
  "violations": [{rule_id, description}], "audit_event_id"}`
- `/verify` returns `verdict: "HALT"`, `routing: "COMPLYEDGE_BLOCKED"`, with the same
  payload under `compliance`, so the SDK interceptors stop the agent

If ComplyEdge is unreachable or errors, the call runs without the check (fail-open,
logged). Without the key, EIF makes no ComplyEdge call.

Audit attribution on every check (never a credential):

| Field | Value |
|-------|-------|
| `agent_id` | `eif-mcp` (`COMPLYEDGE_AGENT_ID`) |
| `jurisdiction` | `EU` (`COMPLYEDGE_JURISDICTION`) |
| `context.user_id` | `eifkey:` + first 12 hex of SHA-256 of the caller's EIF key; `local:<login>` over stdio or an open dev server |
| `context.user_role` | `mcp_client` (MCP over HTTP), `sdk_client` (`/verify`), `maintainer` (local) |
| `context.session_id` | the EIF `session_id` when the call has one, else the MCP session |

Env: `COMPLYEDGE_API_KEY`, `COMPLYEDGE_API_URL` (default `https://api.complyedge.io`),
`COMPLYEDGE_AGENT_ID`, `COMPLYEDGE_JURISDICTION`, `COMPLYEDGE_TIMEOUT_S` (default 5).
Tests: `tests/unit/test_runtime_compliance.py`. Intent:
`eif/mcp_server/runtime_compliance_intent.yaml`.

---

## Public surfaces

| Surface | URL |
|---------|-----|
| Enforcement seal (SVG) | https://api.complyedge.io/v1/public/badge/eif.svg |
| Trust JSON | https://api.complyedge.io/v1/public/trust/eif |
| Trust page | https://trust.complyedge.io/eif |
| Origin site | https://github.com/leocelis/eif |

The seal reflects **live runtime audit data** (checks in 24h / 30d). It is not a static marketing badge.

---

## LLM-facing scan scope

| Path | Role |
|------|------|
| `eif/**/*_intent.yaml` (15 files) | IVD-style intent artifacts - constraints the engine's design was built against |

Scope is set in `.trustlint.yaml` and mirrored in `scripts/compliance/check.sh`'s `find` target.

---

## Operator setup (BYOK)

1. Provision a ComplyEdge tenant with slug `eif` and store the API key in env only: `COMPLYEDGE_API_KEY` (GitHub Actions secret for the optional runtime job, never in git).
2. Enable public trust:

```bash
curl -s -X PATCH https://api.complyedge.io/v1/tenant/trust \
  -H "Authorization: Bearer $COMPLYEDGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"trust_public_enabled": true, "public_slug": "eif", "display_name": "EIF - Epistemic Integrity Framework", "website_url": "https://github.com/leocelis/eif"}'
```

3. Seed runtime checks (feeds the live seal):

```bash
export COMPLYEDGE_API_KEY=ce_...
./scripts/compliance/runtime_check.sh
```

---

## CI

| Job | Path | Secret required |
|-----|------|-----------------|
| `test` | `pytest` (3.11, 3.12 matrix) | None |
| `lint` | `ruff check` | None |
| `compliance` | `./scripts/compliance/check.sh` | None |
| `compliance-runtime` (optional) | `./scripts/compliance/runtime_check.sh` | `COMPLYEDGE_API_KEY` |

Offline gate is the auditable merge blocker. Runtime is opt-in proof for live trust metrics; it runs only on push to `main` and skips cleanly when the secret is absent.

---

## Local validation

```bash
pip install 'trustlint>=2.0.1'
./scripts/compliance/check.sh
export COMPLYEDGE_API_KEY=ce_...
./scripts/compliance/runtime_check.sh
```

---

## References

- Offline gate script: `scripts/compliance/check.sh`
- Runtime probe script: `scripts/compliance/runtime_check.sh`
- TrustLint config: `.trustlint.yaml`
- ComplyEdge API reference: https://complyedge.io/docs/api-reference.html
- Same pattern: [leocelis/ivd](https://github.com/leocelis/ivd), [leocelis/horizon](https://github.com/leocelis/horizon)

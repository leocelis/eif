# EIF in Cursor (via MCP)

EIF ships a FastMCP server exposing 25 tools. The six you will touch most:

| Tool | What it does |
|---|---|
| `eif_new_session` | Create a session; every other stateful tool requires its session_id |
| `eif_extract_claims_from_decision` | Turn a plain-text decision into structured claims ranked by HALT probability |
| `eif_verify` | One-call full pipeline: declare, falsify, calibrate, route. Returns PASS or HALT |
| `eif_get_context` | Load EIF thresholds and the pipeline quick reference (granular pipeline only) |
| `eif_demo` | Zero-setup HALT example, no API calls |
| `eif_check_rules_installed` | Confirm the rules block below is installed |

The MCP contract is identical to Claude Code and Claude Desktop. See the
[integration index](./README.md) for the canonical rules block.

---

## 1. Register in Cursor

### Option A - hosted endpoint (zero install, private alpha)

Request a key by [opening a Discussion](https://github.com/leocelis/eif/discussions), then add to `~/.cursor/mcp.json`:

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

Reload the MCP panel (Cursor Settings, Features, Model Context Protocol,
toggle off and on). The 25 tools appear immediately.

> The hosted endpoint is in private alpha and key-protected (Bearer token,
> constant-time comparison, rate-limited). Options B and C run fully on your
> own machine with no key.

### Option B - local venv (stdio, fully self-hosted)

```bash
pip install eif-engine
```

Add to `~/.cursor/mcp.json`, replacing the Python path with your venv:

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

### Option C - workspace scope (`.cursor/mcp.json`)

Useful when you want EIF in one project only. Same JSON as Option B in
`.cursor/mcp.json` at the workspace root, or the zero-install form:

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

---

## 2. Install the rules block as a Cursor rule

Create `.cursor/rules/eif.mdc` in your workspace (this exact path is one of
the defaults `eif_check_rules_installed` looks for):

```
---
description: EIF - verify load-bearing claims before acting on them
alwaysApply: true
---

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

Legacy alternative: append the same block (without the `---` frontmatter) to
`.cursorrules` at the workspace root. Both locations are detected by
`eif_check_rules_installed`.

---

## 3. Verify the install

1. In the Cursor agent panel, ask for `eif_demo`. It returns a complete
   pre-built HALT response with zero API calls; if you get the Manor Lords
   scenario back, the server works end to end.
2. Ask the agent to run the real cold-start loop on a decision you give it:
   `eif_new_session` (store the `session_id`), then
   `eif_extract_claims_from_decision`, then `eif_verify(session_id=...)`.
   A `HALT` or `PASS` verdict with `halt_cards` or evidence confirms the
   full pipeline, not just the demo.
3. Ask the agent to run `eif_check_rules_installed`. With a local (stdio)
   server, pass absolute paths:

```
eif_check_rules_installed(file_paths=["/Users/you/workspace/.cursor/rules/eif.mdc"])
```

> `eif_check_rules_installed` reads files on the machine where the MCP server
> runs. This works with local (stdio) servers. With the hosted endpoint,
> validate locally instead: `grep "<BEGIN-EIF" .cursor/rules/eif.mdc`.

---

## 4. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Tools don't appear | MCP panel not reloaded after config edit | Toggle the MCP feature off and on, or restart Cursor |
| Agent never calls `eif_verify` | Rule not installed or `alwaysApply` missing | Create `.cursor/rules/eif.mdc` from section 2 with `alwaysApply: true` |
| `eif_check_rules_installed` returns `installed: false` for a file you know exists | Hosted server cannot read your filesystem, or relative paths resolved against the server CWD | Use a local (stdio) server for this check, pass absolute paths, or validate with `grep` |
| Hosted endpoint returns auth errors | Missing or wrong Bearer key | Re-check the `Authorization` header; request a key via GitHub Discussions |
| `uvx eif-engine` fails | Package name is not the executable name | Use `uvx --from eif-engine eif-mcp-server` |

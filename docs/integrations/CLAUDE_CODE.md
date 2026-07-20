# EIF in Claude Code (via MCP)

EIF ships a FastMCP server exposing 25 tools. The six you will touch most:

| Tool | What it does |
|---|---|
| `eif_new_session` | Create a session; every other stateful tool requires its session_id |
| `eif_extract_claims_from_decision` | Turn a plain-text decision into structured claims ranked by HALT probability |
| `eif_verify` | One-call full pipeline: declare, falsify, calibrate, route. Returns PASS or HALT |
| `eif_get_context` | Load EIF thresholds and the pipeline quick reference (granular pipeline only) |
| `eif_demo` | Zero-setup HALT example, no API calls |
| `eif_check_rules_installed` | Confirm the rules block below is installed |

The MCP contract is identical to Cursor and Claude Desktop. See the
[integration index](./README.md) for the canonical rules block.

---

## 1. Register in Claude Code

Three options in order of setup time:

### Option A - hosted endpoint (zero install, private alpha)

Request a key by [opening a Discussion](https://github.com/leocelis/eif/discussions), then run:

```bash
# User scope: available in every project
claude mcp add --transport sse eif https://eif.leocelis.com/sse \
  --header "Authorization: Bearer YOUR_KEY_HERE" \
  --scope user
```

Verify:

```bash
claude mcp get eif
```

> The hosted endpoint is in private alpha and key-protected (Bearer token,
> constant-time comparison, rate-limited). Options B and C run fully on your
> own machine with no key.

### Option B - local venv (stdio, fully self-hosted)

```bash
pip install eif-engine
claude mcp add eif -- /path/to/venv/bin/python -m eif.mcp_server.server --scope user
```

### Option C - project scope (`.mcp.json`)

Useful when you want EIF in one repo only. Create `.mcp.json` at the project
root:

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

Or the zero-install local form:

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

Claude Code picks up `.mcp.json` automatically and prompts for trust approval
on first use.

---

## 2. Install the rules block in `~/.claude/CLAUDE.md`

Claude Code reads `~/.claude/CLAUDE.md` as global instructions for every
session. Append the block below so the agent runs the verification loop
without being asked. For a single project, put the same block in the
project's `CLAUDE.md` instead.

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

---

## 3. Allow EIF tools without per-call approval

Without an allowlist entry, Claude Code prompts for approval on every tool
call. The verification tools are read-only against your project (they verify
claims; they do not modify files), so they are safe to auto-allow:

**`~/.claude/settings.json`** (or project `.claude/settings.json`):

```json
{
  "permissions": {
    "allow": [
      "mcp__eif__eif_new_session",
      "mcp__eif__eif_get_context",
      "mcp__eif__eif_extract_claims_from_decision",
      "mcp__eif__eif_verify",
      "mcp__eif__eif_demo",
      "mcp__eif__eif_check_rules_installed"
    ]
  }
}
```

Add the granular pipeline tools (`eif_declare`, `eif_falsify`, and the rest)
to the list if you use the step-by-step flow.

---

## 4. Verify the install

```bash
# Server registered?
claude mcp list
```

Inside a session:

1. Ask Claude to run `eif_demo`. It returns a complete pre-built HALT response
   with zero API calls; if you get the Manor Lords scenario back, the server
   works end to end.
2. Ask Claude to run the real cold-start loop on a decision you give it:
   `eif_new_session` (store the `session_id`), then
   `eif_extract_claims_from_decision`, then `eif_verify(session_id=...)`.
   A `HALT` or `PASS` verdict with `halt_cards` or evidence confirms the
   full pipeline, not just the demo.
3. Ask Claude to run `eif_check_rules_installed` with absolute paths:

```
eif_check_rules_installed(file_paths=["/Users/you/.claude/CLAUDE.md"])
```

> `eif_check_rules_installed` reads files on the machine where the MCP server
> runs. This works with local (stdio) servers. With the hosted endpoint,
> validate locally instead: `grep "<BEGIN-EIF" ~/.claude/CLAUDE.md`.

---

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Tools don't appear | Server not registered or wrong scope | `claude mcp list`; re-add with the correct `--scope` |
| Per-call approval dialogs | No allowlist in `settings.json` | Add the `permissions.allow` snippet from section 3 |
| Agent never calls `eif_verify` | Rules block not installed | Append the block from section 2 to `~/.claude/CLAUDE.md` |
| `eif_check_rules_installed` returns `installed: false` for a file you know exists | Hosted server cannot read your filesystem, or relative paths resolved against the server CWD | Use a local (stdio) server for this check, pass absolute paths, or validate with `grep` |
| Hosted endpoint returns auth errors | Missing or wrong Bearer key | Re-check the `Authorization` header; request a key via GitHub Discussions |
| `uvx eif-engine` fails | Package name is not the executable name | Use `uvx --from eif-engine eif-mcp-server` |

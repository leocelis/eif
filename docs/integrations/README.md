# EIF integration index

EIF ships a FastMCP server exposing 25 tools. Any MCP client can use it; these
guides cover the three most common ones. Pick the doc for your client:

| Client | Guide | MCP config location | Rules location |
|---|---|---|---|
| Claude Code (CLI) | [CLAUDE_CODE.md](./CLAUDE_CODE.md) | `claude mcp add` or project `.mcp.json` | `~/.claude/CLAUDE.md` |
| Cursor (IDE agent) | [CURSOR.md](./CURSOR.md) | `~/.cursor/mcp.json` | `.cursor/rules/eif.mdc` |
| Claude Desktop | [CLAUDE_DESKTOP.md](./CLAUDE_DESKTOP.md) | `claude_desktop_config.json` | Project instructions |
| ComplyEdge (case study) | [COMPLYEDGE.md](./COMPLYEDGE.md) | n/a | n/a |

## The common contract

Every client ultimately uses the same three-tool path:

1. `eif_new_session()` creates a session and returns `session_id`. Every
   other stateful tool requires it; call it once per decision or task, not
   once per claim.
2. `eif_extract_claims_from_decision(decision)` turns a plain-text agent
   decision into 2-4 structured claims ranked by HALT probability.
3. `eif_verify(session_id, decision, claims)` runs the full pipeline and
   returns PASS or HALT with evidence and a cost figure.

The granular pipeline (`eif_declare` through `eif_record`) is available in all
clients for step-by-step control. See the [main README](../../README.md) for
the full tool table.

## The agent rules block (canonical)

This is the canonical text of the EIF rules block. Each client guide embeds
the same block; if you edit it here, update the client guides and the main
README to match. `eif_check_rules_installed` detects any `<BEGIN-EIF vX.Y>`
marker, so older v1.0 installs remain valid until you refresh them.

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

## Verifying an install

`eif_check_rules_installed` reads files on the machine where the MCP server
process runs. With a local (stdio) server that is your machine, so pass
absolute `file_paths[]` and it will find your instruction files. With the
hosted endpoint the server cannot see your filesystem; validate locally
instead:

```bash
grep -l "<BEGIN-EIF" ~/.claude/CLAUDE.md .cursor/rules/eif.mdc .cursorrules AGENTS.md 2>/dev/null
```

Any hit means the block is installed for that surface.

# EIF in Claude Desktop (via MCP)

Claude Desktop has first-class MCP support. The MCP contract is identical to
Claude Code and Cursor: the same 25 tools work in all three clients. See the
[integration index](./README.md) for the canonical rules block.

---

## 1. Register in Claude Desktop

Edit `claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### Option A - hosted endpoint (zero install, private alpha)

Request a key by [opening a Discussion](https://github.com/leocelis/eif/discussions), then add:

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

Restart Claude Desktop. The tools appear in the MCP panel immediately.

> The hosted endpoint is in private alpha and key-protected (Bearer token,
> constant-time comparison, rate-limited). Options B and C run fully on your
> own machine with no key.

### Option B - local venv (stdio, fully self-hosted)

```bash
pip install eif-engine
```

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

### Option C - uvx (zero install, self-hosted)

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

Restart Claude Desktop after any config change.

---

## 2. Project instructions

Claude Desktop has no `CLAUDE.md`; put the rules block in your Claude
Project's custom instructions (or paste it at the start of a conversation)
so the agent runs the verification loop without being asked:

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

## 3. Verify the install

1. Ask Claude to run `eif_demo`. It returns a complete pre-built HALT response
   with zero API calls; if you get the Manor Lords scenario back, the server
   works end to end.
2. Ask Claude to describe a decision, then watch for `eif_new_session`
   followed by `eif_extract_claims_from_decision` and `eif_verify` (with the
   returned `session_id`) in the tool call log.

> `eif_check_rules_installed` reads files on the machine where the MCP server
> runs, so it cannot see Claude Desktop Project instructions. Verify by
> behavior (step 2) instead.

---

## 4. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Tools don't appear | Config not reloaded | Fully quit and restart Claude Desktop |
| JSON config rejected | Trailing comma or wrong nesting | Validate the file with `python -m json.tool` |
| Agent never calls `eif_verify` | Rules block not in Project instructions | Add the block from section 2 |
| Hosted endpoint returns auth errors | Missing or wrong Bearer key | Re-check the `Authorization` header; request a key via GitHub Discussions |
| `uvx eif-engine` fails | Package name is not the executable name | Use `uvx --from eif-engine eif-mcp-server` |

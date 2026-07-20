# Changelog

All notable changes to `eif-engine` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [4.1.0] - 2026-07-19

### Added
- Optional hosted MCP endpoint (private alpha) at `eif.leocelis.com`, serving both
  streamable-http (`/mcp`) and SSE (`/sse` + `/messages`) transports with a single
  Bearer key. LEGAL.md, TERMS_OF_SERVICE.md, and PRIVACY_POLICY.md updated to
  describe the resulting data flow (in-memory only, never logged or persisted).
- ComplyEdge TrustLint live trust badge and `docs/integrations/COMPLYEDGE.md`.
- P0 host-tool numeric comparison: claims and evidence carrying numbers are now
  compared directly (2% tolerance) instead of by keyword overlap alone.
- `ruff` lint job in CI.
- Governance and legal suite: CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, LEGAL,
  TERMS_OF_SERVICE, PRIVACY_POLICY, DATA_PROCESSING_AGREEMENT (template),
  DECISIONS (ADR log), NOTICE, CHANGELOG.
- CI: test matrix (Python 3.11, 3.12) plus TrustLint EU AI Act screening of
  intent artifacts and an optional ComplyEdge runtime probe (BYOK).
- TrustLint offline compliance gate (`.trustlint.yaml`,
  `scripts/compliance/check.sh`) and matching pre-commit hook.
- `py.typed` marker and ruff configuration.
- Landing page (`index.html`), kept in-repo; GitHub Pages is not enabled.

### Changed
- Repository restructured for public release: internal and venture material
  moved out of the OSS tree.
- Billing and hosted-service surfaces removed from the OSS tree. EIF is a pure
  self-host project by default: pip install from source, stdio MCP server
  (`eif-mcp-server`), optional local HTTP server (`eif-mcp-http-server`),
  Docker.
- LEGAL.md and TERMS_OF_SERVICE.md (now v1.2): added an age-eligibility clause
  (18+) and identity/accountability language for hosted-alpha key requests, a
  CSAM/child-safety prohibition, a Miscellaneous section (entire agreement,
  severability, no waiver, no assignment, force majeure), an exhaustive
  no-warranty list naming NIS2 and the Cyber Resilience Act alongside the EU
  AI Act and GDPR, a maintainer-position note on EIF's own CRA status
  (believed out of scope as free non-commercial OSS), and a transparency note
  that MIT carries no explicit patent grant. See DECISIONS.md EIF-009.

### Security
- The hosted HTTP server now enforces a per-key rate limit (default 60
  requests/minute, `EIF_RATE_LIMIT_PER_MINUTE`) on `/mcp`, the streamable
  websocket path, and `/verify`. The Terms of Service already prohibited
  DoS-volume usage; nothing technically enforced it until now.
- Fixed a working remote code execution in the P1 code-execution evidence path
  (`collect_code_execution`), found via adversarial testing of the hosted MCP
  endpoint's attack surface and confirmed with a proof-of-concept payload:
  claim text substituted into generated Python source could break out of its
  string literal and, via `().__class__.__bases__[0].__subclasses__()` object
  introspection, reach `os.system` without triggering the existing
  forbidden-imports denylist. Claim text is now passed through `json.dumps()`
  instead of interpolated into source, and the AST validator now rejects any
  dunder-pattern name or attribute access categorically, closing the general
  class of Python sandbox-escape gadgets rather than one specific technique.
  See DECISIONS.md EIF-008. New regression tests in
  `tests/unit/test_p1_sandbox_security.py`.

### Fixed
- P1 code execution was silently non-functional for every claim, benign or
  not: all five templates imported `sys` for control flow, and `sys` is on
  the same AST validator's forbidden-imports list. Templates now use
  `return` inside a wrapped function instead of `sys.exit()`. This also
  happened to be the reason the RCE above was not reachable in the
  previously deployed version.
- `HIGH_RISK_ASSUMED` advisory entries no longer drive the overall verdict to HALT;
  they are surfaced for review but marked non-blocking, matching their documented
  behavior.
- FastMCP's streamable-http lifespan is now forwarded and DNS-rebinding protection
  is disabled in production, fixing the hosted HTTP/SSE transports (previously 421
  behind a reverse proxy).
- Full pre-release audit (85 findings): repaired the three broken integration
  surfaces (eif.auto import crash with the anthropic SDK, eif.integration
  session wiring, HTTP MCP transport wiring, LangChain sync-callback deadlock),
  routed P1 template execution through the AST screen, relabeled built-in
  benchmark constants honestly, removed retention/upsell leftovers, moved the
  server log out of ~/.cursor, corrected stale docs (thresholds, corpus
  numbers, module maps, EU AI Act article), and removed em dashes from all
  prose.

## [4.0.0] - 2026-07-17

### Added
- 8-phase scientific-method pipeline: DECLARE, FALSIFY, CAUSAL_GATE, CALIBRATE,
  CHALLENGE, UPDATE, EXPLAIN, RECORD, routing each turn to ACT, REVISE, or HALT.
- 24 MCP tools exposing the pipeline over stdio and local HTTP transports.
- Evidence trust-weighting: tier-aware and confidence-aware Bayesian likelihood
  with a corroboration gate.
- Auxiliary gates: sycophancy detection (position drift, unfaithful CoT),
  input guard (adversarial input detection), and causal gate (Pearl causal
  levels, confounder and disjunctive-bias flags).
- Validation corpus: 14 illustrative multi-agent scenarios across clinical,
  engineering, compliance, investment, and M&A domains
  (`validation/CORPUS_REPORT.md`).

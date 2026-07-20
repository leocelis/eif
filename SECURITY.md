# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 4.x     | Yes       |
| < 4.0   | No        |

---

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Use GitHub private vulnerability reporting: navigate to the
[Security tab](https://github.com/leocelis/eif/security) on `leocelis/eif` and
click **Report a vulnerability**. This creates a private advisory visible only
to the maintainer, and keeps the report private until a fix is coordinated.

Please include:

1. **Description**: what the vulnerability is and what it allows
2. **Steps to reproduce**: minimal reproducible case
3. **Affected versions**
4. **Impact**: confidentiality, integrity, or availability

---

## Response Expectations

| Stage | Timeline |
|-------|----------|
| Acknowledgment | Within 3 business days |
| Triage and severity assessment | Within 7 business days |
| Fix or mitigation plan communicated | Within 14 business days |
| Public disclosure | Coordinated after a fix is available |

---

## Scope

This policy covers:

- The `eif-engine` Python library (`eif/`)
- The MCP servers (`eif/mcp_server/`): stdio (`eif-mcp-server`) and local HTTP (`eif-mcp-http-server`)
- The P1 code-execution sandbox (`eif/falsify/native_tools.py`): AST validation, subprocess isolation

Out of scope:

- Third-party dependencies (report to their maintainers; transitive CVEs are tracked via Dependabot)
- Forks or derivative works not maintained in this repository
- The security of your own deployment infrastructure (see below)

---

## Self-Hosted Deployments

EIF is self-hosted software. You own the security of your deployment.

- **The HTTP server is intended for local use.** Run it on localhost or inside a
  private network. If you expose it beyond that, set `EIF_API_KEY`, terminate TLS
  in front of it, and restrict access at the network layer.
- **Keys stay out of source control.** Never commit `.env`, `EIF_API_KEY`, or
  `OPENAI_API_KEY`. Copy `.env.example` to `.env` and keep `.env` gitignored.
- **The core engine makes no outbound network calls.** Optional LLM-backed
  helpers only activate when `OPENAI_API_KEY` is set; unset it for fully
  offline operation.
- **The P1 sandbox executes generated Python in a subprocess** after AST-based
  validation. It is designed for EIF's own stdlib-only code templates. Do not
  route untrusted arbitrary code through it.

# AI Agent Compliance Documentation

## For Compliance Officers and Auditors

This page explains what EIF is, what its compliance report documents, and how it can support your organisation's own compliance work under the EU AI Act and equivalent frameworks.

**Read this first:** EIF is informational support for the deployer's compliance programme. It does not satisfy, certify, or guarantee compliance with anything. The authoritative statement of what EIF is and is not, legally, is [LEGAL.md](../LEGAL.md) in the repository root.

---

## What is EIF?

EIF (Epistemic Integrity Framework) is a development-time verification library. Before an AI agent acts on a claim it has generated (a cost figure, a compliance requirement, a causal assertion, a statistical result), EIF checks whether that claim is supported by independent evidence.

When independent evidence contradicts a claim, or when no independent evidence can be found, EIF routes the claim to HALT and records the event. The routing signal is advisory: your code or agent controller decides how to act on it.

EIF's primary path is self-hosted: you run it as a stdio MCP server, an optional local HTTP server (bound to 127.0.0.1 by default, optionally protected by a single `EIF_API_KEY`), or via Docker, entirely on your own infrastructure. An optional private-alpha hosted endpoint also exists (`eif.leocelis.com`) with no account system beyond a Bearer key, no billing, and no telemetry. If your compliance programme requires the categorical "no data leaves my infrastructure" guarantee, self-host; see [PRIVACY_POLICY.md](../PRIVACY_POLICY.md) for the exact difference.

---

## Does EIF make external network calls?

Two, both optional and both under your control:

1. **DuckDuckGo web search (DDGS).** During the FALSIFY phase's P3 evidence tier, EIF issues read-only search queries derived from the claim under test. The claim-derived query text egresses to DuckDuckGo.
2. **OpenAI API.** Only if you set `OPENAI_API_KEY`. Used by the CHALLENGE multi-critic (adversarial critique of surviving claims) and by the causal evidence probe in CAUSAL_GATE. If the key is not set, these features simply do not fire.

No third-party EIF scoring service exists, and none receives your data. Everything else (session state, provenance records, cost ledger) stays local under `~/.eif/`.

---

## What does the compliance report document?

Each compliance report covers one EIF session: a period of AI agent activity during which you ran EIF verification. You generate it yourself with the `eif_compliance_report(session_id)` MCP tool.

For every decision audited, the report records:

| Field | What it means |
|---|---|
| Decision text | The claim or decision the AI agent was about to act on |
| Claim classification | Whether the claim was stated as known fact, assumed, or speculative (GUESSED) |
| Evidence collected | The independent source that supports or contradicts the claim |
| Verdict | PASS (claim supported) or HALT (claim blocked, human review required) |
| Human oversight action | What was done after a HALT |
| Cost consequence | Estimated cost if the blocked claim had been acted on without verification |

---

## How does this relate to EU AI Act articles?

EIF's RECORD phase maps provenance fields to the articles most commonly raised in audits of AI systems used in regulated contexts. This mapping is informational. It supports the deployer's own compliance documentation work; it does not satisfy any article, and it has not been reviewed, certified, or endorsed by any notified body, competent authority, or regulator. See [LEGAL.md](../LEGAL.md).

**Article 9 (Risk Management System)**

Article 9 requires providers of high-risk AI systems to establish, implement, document, and maintain a risk management system that identifies risks and takes risk management measures.

EIF supports the deployer's Article 9 documentation by: (a) classifying every claim the agent makes by its epistemic status before it is acted on, (b) collecting independent evidence to test each claim, and (c) routing to HALT with an escalation record when evidence is insufficient or contradictory. The HALT record is documentation you can cite in your own risk management file; it is not, by itself, a risk management system.

**Article 12 (Record-keeping)**

Article 12 requires high-risk AI systems to enable automatic logging of events, allowing monitoring of the system's operation throughout its lifetime.

EIF maps provenance fields to the documentation needs of Article 12 by producing a JSONL provenance record for every session: full decision context, evidence collected, posterior probability update, and routing verdict. Records are plain local JSONL files. They are not immutable; retention, access control, and integrity protection of these files are the deployer's responsibility.

**Article 14 (Human Oversight)**

Article 14 requires high-risk AI systems to allow effective oversight by natural persons who can understand the system's limitations and intervene when necessary.

EIF supports the deployer's Article 14 documentation because every HALT is an explicit escalation signal for human review. The compliance report documents which decisions were escalated, what the agent was about to act on, and what oversight action was recorded. Designing and operating the actual human oversight process remains the deployer's obligation.

---

## How to retain the audit trail

The compliance report is a human-readable rendering of the session's provenance chain, which you host and own.

1. **Retain the report.** File the generated report with your AI governance documentation.
2. **Export the full provenance.** Generate a machine-readable JSONL export of the session with `eif_compliance_report(session_id)`. It contains every claim, evidence trail, and routing decision.
3. **Protect the source files.** Session records are local JSONL under `~/.eif/`. Apply your own backup, access-control, and integrity measures (for example checksums or WORM storage) if your framework requires tamper-evident logs.
4. **Retention period.** The EU AI Act does not specify a retention period for Article 9 risk management records, but GDPR Article 5(1)(e) and sector regulations may apply. Retain according to the most specific regulation applicable to your sector, on advice of your counsel.

---

## Where to find more documentation

Since you host EIF yourself, everything is generated from your own deployment:

- Full JSONL provenance export for a session: `eif_compliance_report(session_id)`
- Session state, registry, provenance, programme health, calibration: the `eif://session/{id}/...` MCP resources
- Evidence collection methodology: [architecture.md](architecture.md) in this docs folder
- Legal scope, disclaimers, and the authoritative EU AI Act positioning: [LEGAL.md](../LEGAL.md)

---

## Scope and limitations

EIF verifies epistemic claims: assertions of fact, causation, cost, or compliance status made by an AI agent with high confidence. It does not:

- Satisfy, certify, or guarantee compliance with the EU AI Act or any other regulation
- Replace a Data Protection Impact Assessment (DPIA) under GDPR
- Constitute legal advice or a legal opinion
- Guarantee that a claim routed to ACT is true, or that a claim routed to HALT is false
- Verify claims outside the scope of evidence retrievable from your tools, your code, or public sources (for example internal company policy or privileged documents, unless you register a host tool that can reach them)

EIF is one component of an AI governance programme, not a substitute for one.

---

## Version

EIF Engine v4.0.0 · MIT License · [github.com/leocelis/eif](https://github.com/leocelis/eif)

*For legal notices and disclaimers governing this project, see [LEGAL.md](../LEGAL.md).*

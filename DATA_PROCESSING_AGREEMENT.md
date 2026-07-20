# Data Processing Agreement (Template)

> **Version:** 1.0 · **Effective:** 2026-07-17
>
> **Template. Not in force.** EIF's maintainer does not process user data (see
> [PRIVACY_POLICY.md](PRIVACY_POLICY.md)), so no DPA with the maintainer exists or is
> needed. This template is provided as a convenience for organizations that deploy
> EIF's HTTP server (`eif-mcp-http-server`) internally and need a GDPR Art. 28
> agreement **between their own controller and processor entities** (for example, a
> parent company and the subsidiary or internal service team operating the EIF
> deployment). Have your own counsel review and adapt it before use. It creates no
> obligations for, and grants no rights against, the EIF maintainer.

---

## Parties

- **Controller:** `[LEGAL ENTITY NAME, REGISTERED ADDRESS]` ("Controller")
- **Processor:** `[LEGAL ENTITY NAME, REGISTERED ADDRESS]` ("Processor")

This Data Processing Agreement ("DPA") is entered into pursuant to Article 28 of
Regulation (EU) 2016/679 ("GDPR") and forms part of `[MAIN AGREEMENT REFERENCE]`.

---

## 1. Subject Matter and Duration

The Processor operates a deployment of the Epistemic Integrity Framework ("EIF"),
including its HTTP server, on infrastructure under the Processor's control, and
processes personal data contained in claims, evidence, session stores, cost ledgers,
and provenance records on the Controller's behalf.

This DPA applies for the duration of `[MAIN AGREEMENT REFERENCE]` and until all
personal data processed under it is deleted or returned per §9.

---

## 2. Nature and Purpose of Processing

Verification of AI agent claims through EIF's pipeline: claim extraction, evidence
collection, Bayesian calibration, routing (ACT/REVISE/HALT), and generation of
provenance records, together with storage of the resulting local artifacts.

`[ADAPT: describe your deployment's actual purpose and any enabled optional features,
including outbound evidence collection (DuckDuckGo) and OpenAI-backed critique, which
transmit claim text to those third parties.]`

---

## 3. Categories of Data and Data Subjects

- **Data categories:** `[e.g., personal data appearing in agent claims and evidence,
  identifiers in session metadata, personal data captured in provenance records]`
- **Data subjects:** `[e.g., employees, customers, end users of the Controller's AI
  systems]`
- **Special categories (Art. 9):** `[none / specify, with the legal basis]`

---

## 4. Processor Obligations

The Processor shall:

1. Process personal data only on documented instructions from the Controller,
   including with regard to transfers to third countries (Art. 28(3)(a))
2. Ensure persons authorized to process the data are bound by confidentiality
   (Art. 28(3)(b))
3. Implement the technical and organizational measures in §5 (Art. 32)
4. Respect the sub-processor conditions in §6 (Art. 28(2), 28(4))
5. Assist the Controller in responding to data subject rights requests, taking into
   account the nature of the processing (Art. 28(3)(e))
6. Assist the Controller with security, breach notification, and data protection
   impact assessment obligations (Arts. 32 to 36), including notifying the Controller
   without undue delay after becoming aware of a personal data breach
7. Delete or return personal data per §9 (Art. 28(3)(g))
8. Make available information necessary to demonstrate compliance and allow audits
   per §7 (Art. 28(3)(h)), informing the Controller if an instruction infringes the
   GDPR

---

## 5. Security Measures

At minimum, the Processor shall:

- Keep the EIF HTTP server bound to loopback (127.0.0.1) or otherwise restrict it to
  networks under the Processor's control, and enable bearer authentication
  (`EIF_API_KEY`) where the server is reachable beyond a single host
- Protect local artifacts (session store and cost ledger under `~/.eif/`, provenance
  records) with appropriate filesystem permissions and encryption at rest
- Restrict and log administrative access to the deployment
- Apply security updates to the deployment environment in a timely manner
- `[ADAPT: add your organization's standard TOMs annex]`

---

## 6. Sub-processors

The Controller `[authorizes / does not authorize]` the engagement of sub-processors.
Authorized sub-processors at signature:

| Sub-processor | Role | Condition |
|---------------|------|-----------|
| `[e.g., OpenAI]` | `[Critic tournament and causal evidence probe, only if enabled]` | `[Data processing terms reference]` |
| `[e.g., search provider]` | `[Web evidence collection, only if enabled]` | `[Terms reference]` |
| `[hosting/infrastructure]` | `[Infrastructure for the deployment]` | `[DPA reference]` |

The Processor shall inform the Controller of intended changes and give the Controller
the opportunity to object. The Processor imposes on each sub-processor the same data
protection obligations as set out in this DPA.

---

## 7. Audit

The Processor shall make available to the Controller all information necessary to
demonstrate compliance with this DPA and shall allow for and contribute to audits,
including inspections, conducted by the Controller or an auditor mandated by the
Controller, on reasonable notice and no more than `[frequency]` absent a specific
incident.

---

## 8. International Transfers

The Processor shall not transfer personal data outside the `[EEA / applicable
territory]` without the Controller's documented instruction and appropriate safeguards
under GDPR Chapter V. Note that enabling EIF's optional outbound evidence features may
constitute such a transfer; they shall remain disabled unless covered by this section.

---

## 9. Deletion and Return

Upon termination of the services, the Processor shall, at the Controller's choice,
delete or return all personal data (including session stores, cost ledgers, provenance
records, and backups) within `[period]`, and certify deletion in writing, unless Union
or Member State law requires further storage.

---

## Signatures

| | Controller | Processor |
|---|---|---|
| Name | `[NAME]` | `[NAME]` |
| Title | `[TITLE]` | `[TITLE]` |
| Date | `[DATE]` | `[DATE]` |
| Signature | | |

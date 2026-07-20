# Legal Notices and Disclaimers

> **Version:** 1.2 · **Effective:** 2026-07-19
>
> This document applies to the Epistemic Integrity Framework ("EIF"): the `eif-engine`
> Python package (version 4.0.0 at the effective date), the bundled MCP servers
> (`eif-mcp-server` for stdio, `eif-mcp-http-server` for optional local HTTP), the
> Docker image built from this repository, and the open-source repository at
> github.com/leocelis/eif.
>
> **This document is not legal advice.** It describes how EIF is designed, what it does
> and does not do, and what responsibilities remain with you as its user or deployer.
> If you are deploying EIF in a regulated context, consult qualified legal counsel
> before proceeding.
>
> **Related documents** (all incorporated into these notices by reference):
> - [TERMS_OF_SERVICE.md](TERMS_OF_SERVICE.md): terms governing the repository,
>   documentation, and project website
> - [PRIVACY_POLICY.md](PRIVACY_POLICY.md): what data flows exist and where your
>   data actually goes
> - [DATA_PROCESSING_AGREEMENT.md](DATA_PROCESSING_AGREEMENT.md): a GDPR Art. 28
>   template for organizations deploying EIF internally (not in force; see its header)
> - [SECURITY.md](SECURITY.md): vulnerability disclosure process
> - [LICENSE](LICENSE): MIT License, which governs the software itself
>
> **Self-hosted by default; an optional hosted alpha exists.** EIF's primary
> distribution is source code you run yourself, with everything on your own
> infrastructure. The maintainer also operates an optional private-alpha hosted MCP
> endpoint (`eif.leocelis.com`) as a zero-install convenience: no account system, no
> billing, no analytics or telemetry. If you use it, your claim text is processed in
> memory on the maintainer's server to run the pipeline and is not logged or written
> to disk. See [PRIVACY_POLICY.md](PRIVACY_POLICY.md) §2 and
> [TERMS_OF_SERVICE.md](TERMS_OF_SERVICE.md) for the full scope.

---

## 1. What EIF Is, and Is Not

The Epistemic Integrity Framework is a **development-time verification library and MCP
server** that applies an 8-phase scientific-method pipeline (DECLARE, FALSIFY,
CAUSAL_GATE, CALIBRATE, CHALLENGE, UPDATE, EXPLAIN, RECORD) to claims made by AI
agents, routing each claim to ACT, REVISE, or HALT. It is:

- A local Python library (`eif-engine`) installed from source, running entirely on
  your machine or infrastructure
- A set of 24 MCP tools exposed over stdio (`eif-mcp-server`) or an optional local
  HTTP server (`eif-mcp-http-server`, bound to 127.0.0.1 by default)
- An open-source project under the MIT License
- A structured skepticism layer: it produces routing signals and provenance records
  that **you or your agent controller choose how to act on**

EIF is **not**:

- A guarantee that any claim it routes to ACT is true, or that any claim it routes to
  HALT is false. Routing decisions are probabilistic outputs of a Bayesian pipeline,
  not factual determinations.
- A source of legal, medical, financial, or professional advice. Nothing EIF outputs,
  including its EU AI Act article mappings, constitutes advice of any kind.
- **Certified EU AI Act compliance tooling.** EIF's RECORD phase maps provenance
  records to articles of Regulation (EU) 2024/1689 as an informational aid. This
  mapping supports the deployer's own compliance documentation work; it has not been
  reviewed, certified, or endorsed by any notified body, competent authority, or
  regulator, and producing it does not make any system compliant. See §5.
- A hallucination prevention system or output correctness guarantor
- A substitute for human review, professional judgment, or domain-specific evaluation
- Safe for fully autonomous use in contexts where an incorrect ACT or a missed HALT
  could cause physical, financial, or legal harm without human review. See §3 and §5.

**Classification note (EU AI Act):** the EIF core engine makes no LLM calls and
performs deterministic and Bayesian computation over claims supplied to it. When the
optional OpenAI-backed features are enabled (critic tournament, causal evidence probe),
EIF orchestrates calls to a third-party AI system under your own API key. In either
configuration, when EIF is embedded in a high-risk AI pipeline under Annex III of the
EU AI Act, the high-risk obligations fall on **you** as the deployer of the overall
system. EIF's classification has not been legally certified and is not binding on any
competent authority.

**Classification note (EU Cyber Resilience Act, Regulation (EU) 2024/2847):** EIF is
free, MIT-licensed software distributed on a non-commercial basis, with no purchase
price, no paid tiers, and no revenue tied to distribution. The Cyber Resilience Act's
recitals and Article 2 scope free and open-source software developed or supplied
outside the course of a commercial activity, which is the maintainer's basis for
treating EIF as outside the Act's "manufacturer" obligations. This is the maintainer's
own position, not a legal determination; if you are a commercial entity distributing
EIF (or a product built on it) as part of a commercial offering, you should assess
your own CRA obligations independently, as your distribution may not qualify for the
same treatment.

---

## 2. Performance Claims: Scope and Substantiation

EIF's documentation references quantified figures. Their scope and evidentiary basis:

| Claim | Source | Scope | Limitation |
|-------|--------|-------|------------|
| Validation corpus results (routing counts, detector fires) | 14-scenario validation corpus | **Constructed, illustrative scenarios** authored by the maintainer | Not real agent traffic; not a measurement of production behavior |
| Per-HALT dollar cost estimates (the cost-model feature output, and the figures in `validation/CORPUS_REPORT.md`) | Corpus cost model | **Modeled estimates** derived from assumed domain cost multipliers applied to corpus routings | Not money actually saved or lost by any deployment; the multipliers are assumptions, not observations |
| Any third-party market-size or industry-cost statistic cited anywhere in this repository | The cited third party | Third-party estimate | Not EIF's research; cite the original source for any compliance or commercial purpose |

Full corpus evidence and the cost-model methodology:
[`validation/CORPUS_REPORT.md`](validation/CORPUS_REPORT.md).

**No production performance is claimed.** The corpus demonstrates the mechanisms
(what EIF detects and how it routes) on scenarios built to exercise them. It does not
establish precision, recall, false-positive rates, or cost impact in your domain, with
your models, on your traffic. Do not represent corpus figures as applicable to your
system without conducting your own evaluation, and do not use them in marketing,
regulatory filings, or customer commitments as if they were measured results.

---

## 3. Inherent Limitations of EIF's Method

These are architectural properties of the design, not bugs awaiting a fix. **Each is
your risk to manage in your deployment.**

### 3.1 Bayesian posteriors depend on priors and evidence quality

EIF's CALIBRATE and UPDATE phases compute posterior confidence from priors and
collected evidence. A miscalibrated prior, thin evidence, or evidence that is itself
wrong will produce a confidently wrong posterior. The pipeline is only as good as what
feeds it.

### 3.2 Web evidence can be wrong

The optional evidence collection path queries DuckDuckGo search. Search results can be
outdated, incorrect, adversarially seeded, or simply irrelevant, and EIF cannot fully
distinguish authoritative sources from unreliable ones. Evidence gathered from the web
should be treated as a signal, not ground truth.

### 3.3 Routing produces false positives and false negatives

HALT and ACT routing can be wrong in both directions: a sound claim can be halted
(false positive, costing you time and blocked work) and an unsound claim can be routed
to ACT (false negative, letting an error through). No corpus result bounds these rates
for your domain. Treat every routing decision as advisory unless you have validated
the rates on your own labelled data.

### 3.4 Detectors are heuristic

The sycophancy gate, input guard, reasoning-theater checks, and related detectors are
heuristic pattern detectors. They will miss some manipulative or sycophantic behavior
and will flag some benign behavior. They are tripwires, not proofs.

### 3.5 The critic is only as good as its model

When the optional critic tournament and causal evidence probe are enabled, their
quality depends entirely on the OpenAI model you configure. Model updates, outages, or
degraded outputs on the provider's side change EIF's behavior without any change to
EIF's code.

---

## 4. Third-Party Services

The EIF core engine makes **no external network calls**. Two optional features do, and
both call out **directly from your machine** under your own configuration:

| Service | Trigger | Your relationship |
|---------|---------|-------------------|
| DuckDuckGo search (via the `ddgs` library) | Optional web evidence collection during FALSIFY | Queries go from your machine to DuckDuckGo under DuckDuckGo's own terms |
| OpenAI API | Only if you set `OPENAI_API_KEY`; used by the critic tournament and the causal evidence probe | Your API key, your OpenAI account, OpenAI's terms and pricing, your bill |

The maintainer is not a party to either data flow, receives none of the transmitted
content, and has no control over the availability, terms, pricing, or data handling of
these providers. Claim text sent to these services leaves your machine: do not enable
these features on claims containing personal data, secrets, or confidential business
information unless your own agreements with those providers cover that transmission.

A third flow exists only if you choose the optional hosted alpha endpoint instead of
self-hosting: claim text is then sent to the maintainer's own infrastructure. That
flow is not a third-party service, is not enabled by default, and is described fully
in §1's callout and in [PRIVACY_POLICY.md](PRIVACY_POLICY.md) §1 and §5.

---

## 5. Deployer Obligations

When you build or operate AI systems that use EIF, you are the deployer of those
systems. EIF's role as a library does not transfer, share, or reduce your legal
obligations.

- **EU AI Act (Regulation (EU) 2024/1689):** if your system falls under Annex III
  high-risk categories, the obligations of Articles 9 through 16 apply to your system
  regardless of which libraries it uses. EIF's provenance records and article mappings
  may be useful inputs to your documentation; they are not a conformity assessment and
  do not discharge any obligation.
- **GDPR (Regulation (EU) 2016/679), where applicable:** if claims processed through
  EIF contain personal data, you are the controller (or processor) for that
  processing, including any transmission to DuckDuckGo or OpenAI that you enable, and
  for the local artifacts EIF writes (session store, cost ledger, provenance records).
- **Sector rules:** healthcare, financial services, legal services, and other
  regulated sectors impose their own requirements on AI-assisted decisions. Using EIF
  in a high-stakes domain does not satisfy any of them. In such domains, every EIF
  routing decision should pass human review before action.

---

## 6. No Warranty and Limitation of Liability

The software is licensed under the MIT License, and the following is consistent with
it:

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Without limiting the above, no warranty is made that:

- Routing decisions (ACT, REVISE, HALT), posteriors, detector fires, or provenance
  records will be accurate, complete, or fit for any purpose
- Use of EIF will make any system compliant with any law, regulation, or standard,
  including the EU AI Act and GDPR
- Corpus or cost-model figures will replicate in any real deployment
- The software is free of defects or security vulnerabilities
- The P1 code-execution sandbox, the hosted alpha endpoint, or any other component is
  secure against a sufficiently motivated attacker; see SECURITY.md for known
  considerations and how to report a vulnerability
- Uptime, availability, or uninterrupted service of the hosted alpha endpoint
- Non-infringement of third-party intellectual property rights beyond what the MIT
  License covers for the code itself

**Use of EIF does not guarantee that your AI system will comply with any law,
regulation, or standard**, including but not limited to the EU AI Act, GDPR,
CCPA/CPRA, NIS2, the Cyber Resilience Act, or any sector-specific regulation.

All uses of EIF, including uses and risks not enumerated in this document, are at your
own risk. This document identifies known and foreseeable risks; it is not an
exhaustive enumeration of all risks you may encounter. Some jurisdictions do not allow
certain warranty exclusions or liability limitations; where such restrictions apply,
the above applies to the fullest extent permitted by applicable law.

---

## 7. Indemnification

**To the maximum extent permitted by applicable law**, you agree to defend, indemnify,
and hold harmless Leo Celis, the EIF project, its contributors, and its maintainers
from and against any and all claims, damages, obligations, losses, liabilities, costs,
or expenses (including reasonable legal fees) arising from:

1. Your use of EIF, whether self-hosted or via the hosted alpha endpoint
2. Any AI system, workflow, product, or service you build using EIF
3. Any action taken (or not taken) by you or your agent controller in response to an
   EIF routing decision (ACT, REVISE, or HALT), regardless of whether that decision
   was correct
4. Claim or evidence text you transmit to DuckDuckGo, OpenAI, or the hosted alpha
   endpoint, including any personal data or confidential information contained in it
5. Your violation of any applicable law in connection with your use of EIF, including
   the EU AI Act, GDPR, CCPA/CPRA, or equivalent regulations in your jurisdiction
6. Any claim by a third party that your AI system caused harm or violated rights
7. Your misrepresentation of EIF's capabilities, validation status, or EU AI Act
   coverage to any third party, customer, regulator, or auditor (see §2)

This indemnification obligation survives termination or discontinuation of your use
of EIF.

---

## 8. Trademarks and Attribution

Copyright © 2026 Leo Celis.

"EIF" and "Epistemic Integrity Framework", as used to identify this project, are names
under use by Leo Celis. The MIT License grants broad rights to use, modify, and
redistribute the code; it does not grant the right to represent forks, derivatives, or
third-party services as the official EIF project or as endorsed by its maintainer.

If you publish work that builds on EIF, attribution to the project repository
(github.com/leocelis/eif) is appreciated. If you redistribute the software, retain the
copyright and license notice as the MIT License requires.

**Patents:** the MIT License, unlike Apache-2.0, contains no explicit patent grant or
defensive-termination clause. Courts have generally read an implied patent license
into MIT-licensed code, but this is less certain than an explicit grant. This is a
property of the license the project uses, consistent with the maintainer's other
open-source projects; it is noted here for transparency, not as an offer to relicense.

---

## 9. Governing Law and Jurisdiction

This document and all disputes arising from your use of EIF are governed by the laws
of the **State of Florida, United States**, without regard to its conflict-of-law
provisions.

Any legal action or proceeding must be brought exclusively in the state or federal
courts located in **Broward County, Florida, United States.** You irrevocably consent
to the personal jurisdiction and venue of those courts.

**EU users note:** nothing in this section limits mandatory consumer or data-subject
rights available under EU law, including rights under GDPR, the EU AI Act, or
applicable EU consumer protection law. EU-resident users retain those rights
regardless of this choice-of-law clause.

---

## 10. Changes to This Document

The version number and effective date at the top of this file reflect the last
revision. Changes are tracked in [`CHANGELOG.md`](CHANGELOG.md). If you rely on this
document for compliance purposes, monitor the repository or periodically review the
effective date.

---

*This document is not legal advice. Consult qualified legal counsel before making
compliance or legal decisions based on this text.*

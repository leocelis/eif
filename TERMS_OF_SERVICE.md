# Terms of Service

> **Version:** 1.2 · **Effective:** 2026-07-19
>
> These Terms govern your use of the EIF **repository, documentation, project
> website, and the optional hosted MCP endpoint** at `eif.leocelis.com`
> (collectively, the "Project Materials") at github.com/leocelis/eif.
>
> **The software itself is governed by the MIT License** (see [LICENSE](LICENSE)).
> Where these Terms and the MIT License overlap with respect to the source code, the
> license controls. These Terms add nothing to, and take nothing from, the rights the
> MIT License grants you in the code.
>
> **Self-hosting requires no acceptance of anything beyond the MIT License.** The
> hosted-endpoint terms in §7 below apply only if you choose to use
> `eif.leocelis.com` instead of running EIF yourself.

**Provider:** Leo Celis (the "maintainer")
**Repository:** https://github.com/leocelis/eif

---

## 1. Acceptance

By accessing the Project Materials, opening issues or discussions, submitting
contributions, or otherwise using the repository beyond exercising your MIT License
rights in the code, you accept these Terms. If you do not accept them, limit your use
to what the MIT License grants.

Interactions hosted on GitHub (repository access, issues, discussions, pull requests)
are additionally subject to GitHub's own terms of service.

---

## 2. Intellectual Property

The Project Materials are © 2026 Leo Celis. The source code is licensed under the MIT
License. Documentation in this repository may be reproduced with attribution to the
project. The project names ("EIF", "Epistemic Integrity Framework") may not be used to
represent forks, derivatives, or third-party offerings as the official project (see
[LEGAL.md](LEGAL.md) §8).

Contributions you submit (pull requests, patches) are accepted under the MIT License;
by submitting, you represent that you have the right to license the contribution on
those terms.

---

## 3. Acceptable Use

You must not use the Project Materials to:

- Misrepresent EIF's capabilities, validation status, or the nature of its corpus
  figures (which are constructed and modeled; see [LEGAL.md](LEGAL.md) §2) to any
  third party, customer, regulator, or auditor
- Present EIF's EU AI Act mapping as certification or as a substitute for your own
  compliance obligations
- Harass other users, spam issues or discussions, or submit contributions containing
  malicious code
- Transmit, generate, or attempt to generate through the Project Materials any content
  depicting child sexual abuse material (CSAM), or content that sexually exploits or
  endangers a minor. Any such use will be reported to the relevant authorities and
  platform (GitHub) without notice.

---

## 4. Disclaimers

The Project Materials are provided as is, without warranty of any kind. Documentation
may contain errors or become outdated. The disclaimers, limitation-of-liability terms,
and deployer-obligation notices in [LEGAL.md](LEGAL.md) are incorporated into these
Terms by reference.

---

## 5. Limitation of Liability

To the maximum extent permitted by applicable law, the maintainer shall not be liable
for any indirect, incidental, special, consequential, or punitive damages arising out
of or in connection with the Project Materials or the software, and total aggregate
liability shall not exceed the amount you paid the maintainer for the Project
Materials, which is zero.

---

## 6. Indemnification

You agree to defend, indemnify, and hold harmless Leo Celis and the EIF project from
and against any claims, liabilities, damages, costs, and expenses (including
reasonable legal fees) arising from: (a) your use of the Project Materials, whether
self-hosted or via the hosted alpha endpoint; (b) your violation of these Terms;
(c) any AI system you build using EIF; (d) any action taken or not taken in response
to an EIF routing decision; (e) claim or evidence text you transmit through EIF,
including to DuckDuckGo, OpenAI, or the hosted alpha endpoint; (f) your violation of
any applicable law; or (g) your misrepresentation of EIF's capabilities or validation
status to any third party. This obligation survives termination of your use of the
Project Materials.

---

## 7. Hosted Alpha Endpoint

This section applies only if you use the hosted MCP endpoint at `eif.leocelis.com`
instead of self-hosting.

**Age.** You must be at least 18 years old to use the hosted endpoint or request an
API key.

**Identity and accountability.** Keys are distributed by opening a GitHub Discussion
requesting one, so every key request is tied to an identifiable GitHub account. The
maintainer may decline anonymous, throwaway, or unverifiable requests at their sole
discretion, and may use the requester identity supplied at issuance for abuse
response, including revocation and, where necessary, reporting to GitHub.

**Alpha status.** The hosted endpoint is a private alpha, provided on a best-effort
basis. There is no uptime guarantee, no SLA, and no commitment to continued
availability. Access requires a Bearer API key, distributed at the maintainer's
discretion; keys may be revoked or the endpoint discontinued with reasonable notice.

**Acceptable use.** Do not transmit personal data, sensitive personal data, trade
secrets, credentials, or API keys as claim or evidence text to the hosted endpoint.
Do not use the hosted endpoint in volumes that constitute a denial-of-service attack
or that exceed reasonable single-developer use. Do not attempt to circumvent
authentication or rate limiting. This is enforced technically, not just
contractually: the hosted endpoint caps each key at a default 60 requests/minute
(`EIF_RATE_LIMIT_PER_MINUTE`, see `eif/mcp_server/http_server.py`); requests over the
cap receive `429 RATE_LIMITED` (or a websocket close on the streaming transport) and
you must back off rather than retry immediately.

**Session isolation.** Each session is addressed by a randomly generated identifier
(`uuid.uuid4()`, session_id) that is never enumerated or listed back to any client;
practical isolation between sessions depends on that identifier remaining unguessed
and not shared. There is no cross-key session index, so one key cannot browse or
discover another key's sessions, but a leaked or shared session_id can be used by
whoever holds it.

**Data handling.** See [PRIVACY_POLICY.md](PRIVACY_POLICY.md) §2 for what the hosted
endpoint does with your claim text (processed in memory to run the pipeline, not
logged or persisted to disk).

---

## 8. Governing Law and Dispute Resolution

These Terms are governed by the laws of the **State of Florida, United States**,
without regard to its conflict-of-law provisions.

Any dispute arising from these Terms or your use of the Project Materials must be
brought exclusively in the state or federal courts located in **Broward County,
Florida, United States.** You consent to the personal jurisdiction and venue of those
courts. Nothing in this section limits mandatory consumer or data-subject rights
available to you under the law of your own residence.

---

## 9. Miscellaneous

**Entire agreement.** These Terms, together with [LEGAL.md](LEGAL.md) and
[PRIVACY_POLICY.md](PRIVACY_POLICY.md), constitute the entire agreement between you
and the maintainer regarding the Project Materials and supersede any prior
understandings.

**Severability.** If any provision of these Terms is found unenforceable, the
remaining provisions continue in full force.

**No waiver.** Failure by the maintainer to enforce any provision does not
constitute a waiver of the right to enforce it in the future.

**No assignment.** You may not assign these Terms or any rights under them without
the maintainer's prior written consent. The maintainer may assign these Terms
without restriction, including in connection with a transfer of the project.

**Force majeure.** The maintainer is not liable for failures caused by events beyond
reasonable control, including natural disasters, government actions, infrastructure
failures, or third-party service outages (GitHub, DigitalOcean, OpenAI, DuckDuckGo,
or PyPI).

---

## 10. Changes

The maintainer may revise these Terms by updating this file; the version and effective
date above reflect the last revision. Continued use of the Project Materials after a
revision constitutes acceptance. Material changes are noted in
[`CHANGELOG.md`](CHANGELOG.md).

# EIF Decision Log

**Purpose:** Record the architecture and product decisions behind EIF's public
release, including what was removed and why. One entry per decision, ADR pattern.
**Format:** Context / Decision / Rationale / Consequences.

---

## EIF-001: Remove All Paid and Hosted Surfaces from the OSS Tree

**Date:** 2026-07-17
**Status:** Done

**Context:** The pre-release tree contained surfaces built for a hosted offering:
Stripe billing integration, quota tiers, hosted remote endpoints, and upgrade CTAs in
docs and tool responses. No hosted service is offered; shipping those surfaces in an
OSS repo would advertise a product that does not exist and complicate every honest
claim about data collection.

**Decision:** Remove all paid and hosted surfaces from the public tree. The maintainer
preserves that code privately; if a hosted service is ever offered, it ships with its
own terms.

**Rationale:** Pure-OSS adoption and honest claims. The legal suite can now state
flatly: no hosted service, no billing, no telemetry, and the code backs it.

**Consequences:** Smaller public surface, simpler docs, and LEGAL.md / PRIVACY_POLICY.md
can make categorical "no collection" statements. Re-introducing a hosted path later
requires new terms, not an edit to these.

---

## EIF-002: Reframe Corpus Dollar Figures as Modeled and Illustrative

**Date:** 2026-07-17
**Status:** Done

**Context:** The 14-scenario validation corpus reports per-scenario and total
($7,220,000) "cost saved" figures. The scenarios are constructed, and the dollar
values come from assumed domain multipliers, but early drafts read as if they were
measured outcomes.

**Decision:** Label the corpus constructed and illustrative, and all dollar figures
modeled estimates, with a scope note in `validation/CORPUS_REPORT.md` and a
performance-claim section in LEGAL.md (§2).

**Rationale:** Claim honesty. The corpus demonstrates mechanisms; it does not measure
production performance, and presenting modeled numbers as measurements is exactly the
kind of unverified claim EIF exists to catch.

**Consequences:** Marketing loses a punchy but indefensible number; the project gains
figures it can defend. Production claims now require a real field-validation track.

---

## EIF-003: Simplify Auth to a Single Optional EIF_API_KEY

**Date:** 2026-07-17
**Status:** Done

**Context:** The HTTP server carried a tiered HMAC key scheme (per-tier keys, scopes,
rotation machinery) designed for a multi-tenant hosted service.

**Decision:** Replace it with a single optional `EIF_API_KEY` bearer token on
`eif-mcp-http-server`.

**Rationale:** A self-hosted local server needs one shared secret at most; tiers were
a hosted-service concept with no remaining consumer. Less auth code is less attack
surface and less to audit.

**Consequences:** Simpler config and docs. Anyone who genuinely needs multi-tenant
auth is running EIF behind their own gateway, which is where that concern belongs.

---

## EIF-004: Relocate cost_ledger from billing/ to cost_model/

**Date:** 2026-07-17
**Status:** Done

**Context:** The cost ledger (which accumulates modeled savings per routing decision)
lived under `billing/`, a leftover of the hosted design that implied payment
processing.

**Decision:** Move it to `cost_model/`.

**Rationale:** Names are claims. The module tracks modeled savings, not payments;
`billing/` in an OSS tree that handles no money is a standing misstatement.

**Consequences:** Import paths updated; the tree no longer contains a `billing`
namespace, which keeps the "no billing" statement in the legal docs grep-verifiable.

---

## EIF-005: HTTP Server Default Bind Changed from 0.0.0.0 to 127.0.0.1

**Date:** 2026-07-17
**Status:** Done

**Context:** `eif-mcp-http-server` defaulted to binding 0.0.0.0, exposing an
unauthenticated-by-default claim-processing endpoint on every interface of the host.

**Decision:** Default bind is now 127.0.0.1. Non-loopback binding requires an explicit
opt-in, documented alongside the `EIF_API_KEY` option.

**Rationale:** Safe by default for a local development tool. Users who need network
exposure can choose it consciously and pair it with auth.

**Consequences:** Docker and remote-client setups must pass an explicit bind address.
That friction is the point.

---

## EIF-006: Remove Internal Handoff, Feedback, and Red-Team Docs from the Public Tree

**Date:** 2026-07-17
**Status:** Done

**Context:** The tree carried internal working documents: handoff notes, feedback
ledgers, and red-team session records written for the maintainer's own process, not
for users.

**Decision:** Remove them from the public tree; they remain in the maintainer's
private workspace.

**Rationale:** Working notes are not user documentation. Publishing them adds noise
for users and risks leaking process detail that was never written for an external
audience.

**Consequences:** Public docs are user-facing only (README, docs/, validation
reports, legal suite). Internal process artifacts stay internal, per the project's
private-docs discipline.

---

## EIF-007: Reintroduce a Hosted MCP Endpoint as a Private Alpha

**Date:** 2026-07-18
**Status:** Done

**Context:** EIF-001 removed all hosted surfaces for the initial public release.
Zero-install trial (matching the maintainer's other MCP projects, `ivd` and
`horizon`) needed a reachable endpoint without asking every user to clone and run
the server themselves.

**Decision:** Deploy a single hosted instance at `eif.leocelis.com` (DigitalOcean App
Platform), gated by one shared Bearer key (`EIF_API_KEY`), no accounts, no billing.
Update LEGAL.md, TERMS_OF_SERVICE.md, and PRIVACY_POLICY.md to describe the resulting
data flow: claim text sent to the hosted endpoint is processed in memory to run the
pipeline and is not logged or persisted to disk (verified against
`eif/session.py`, which is a pure in-memory store, and `eif/mcp_server/http_server.py`,
which logs only a truncated key id, verdict, and evidence tier).

**Rationale:** Convenience access without reintroducing the billing/tier machinery
EIF-001 removed. The self-host path remains the categorical "nothing leaves your
machine" option; the hosted path is opt-in and disclosed.

**Consequences:** The "no hosted service" language from EIF-001 is no longer
accurate and was replaced everywhere it appeared (LEGAL.md, TERMS_OF_SERVICE.md,
PRIVACY_POLICY.md, docs/architecture.md, docs/compliance.md, index.html). The legal
suite now describes two paths instead of asserting one categorically.

---

## EIF-008: Close a Working RCE in the P1 Code-Execution Path; Fix the Bug That Was Accidentally Masking It

**Date:** 2026-07-19
**Status:** Done

**Context:** Adversarial testing of the hosted endpoint's attack surface found two
independent bugs in `collect_code_execution` (the P1 evidence tier) that combined
into a proof-of-concept remote code execution, confirmed by actually creating a
file on disk from a crafted claim: (1) claim text was substituted into template
string literals via a naive `'"' -> "'"` replace, which a trailing-backslash
payload could still break out of; (2) the AST validator (`_validate_code`)
denylisted specific names (`os`, `subprocess`, ...) but not dunder attribute
access, so `().__class__.__bases__[0].__subclasses__()` followed by a loaded
class's `__init__.__globals__` reached `os.system` without ever writing a
forbidden name. Separately, all five code templates imported `sys` for
`sys.exit(0)` control flow, and `sys` is (correctly) on the forbidden-imports
list, so the AST screen added for a prior fix was silently rejecting every
invocation of P1 code execution regardless of claim content or intent - this
bug happened to make the RCE unreachable in the currently deployed version,
but fixing it (a real functional regression against the README's P1 claim)
without also closing the dunder gap would have reopened the RCE on the next
deploy.

**Decision:** Fix all three together. Templates now receive claim text via
`json.dumps()` (a properly escaped Python string literal substituted as a bare
expression, not interpolated into source) instead of the naive quote-replace.
`_validate_code` now rejects any dunder-pattern `Name` or `Attribute`
categorically, closing the entire class of Python object-introspection sandbox
escapes rather than one specific gadget. All five templates were rewritten to
wrap their body in `def main(): ... \n main()` and use `return` instead of
`sys.exit(0)`, removing the need to import `sys` at all.

**Rationale:** A specific-name denylist cannot close object-introspection
escapes in Python; only rejecting the dunder pattern itself does. String
interpolation into generated source is unsafe regardless of escaping
discipline; a properly serialized literal (`json.dumps`) removes the class of
bug rather than patching one instance of it. Both fixes ship together because
either one alone leaves a gap: the templating fix without the dunder fix still
allows the same gadget through any other future template; the dunder fix
without the templating fix still allows a corrupted-but-syntactically-valid
script assembled from broken-out claim text.

**Consequences:** P1 code execution is now the first time it has been
verified working end-to-end for benign claims across all five templates
(regression tests in `tests/unit/test_p1_sandbox_security.py` cover this).
Four adversarial payloads, including the working proof-of-concept from
discovery, were re-run against the fixed code and produce no observable
side effect - confirmed by checking for the marker file the payload was
designed to create, not just by inspecting the validator's return value.

---

## EIF-009: Legal Hardening Pass Before Public Release

**Date:** 2026-07-19
**Status:** Done

**Context:** Before flipping the repository public, researched what a solo OSS
maintainer's legal setup typically still needs beyond MIT + disclaimers, and
compared EIF's LEGAL.md / TERMS_OF_SERVICE.md against the more mature version of
the same documents already live in the `horizon` and `ivd` repos (`ivd`'s TOS in
particular carries a `Miscellaneous` section EIF lacked; `horizon`'s TOS was
independently being extended with an age/identity/CSAM clause block during the
same window).

**Decision:** Added, matching the sibling-repo pattern rather than inventing new
structure: an age-eligibility clause (18+) and identity/accountability language
for hosted-alpha key requests (tied to the existing GitHub Discussion request
flow); a CSAM/child-safety prohibition in Acceptable Use; explicit documentation
that the rate limit (EIF-008) and session isolation (random UUID, no
cross-key session index) are technical, not just contractual; a Miscellaneous
section (entire agreement, severability, no waiver, no assignment, force
majeure); an exhaustive no-warranty bullet list matching horizon/ivd's pattern,
naming NIS2 and the Cyber Resilience Act alongside the EU AI Act and GDPR; a
maintainer-position note on EIF's own CRA status (free, non-commercial
distribution, believed out of scope under the Act's OSS carve-out, not a legal
determination); and a brief transparency note that MIT (unlike Apache-2.0) has
no explicit patent grant, consistent with the license already used across the
maintainer's other OSS projects.

**Rationale:** Closing gaps a lawyer's checklist would flag (severability,
force majeure, entire agreement, no waiver are near-universal boilerplate;
age/identity gating is standard for a service issuing access credentials) and
matching the maintainer's own established, more complete pattern rather than
leaving EIF's legal suite less protective than the sibling projects for no
reason. The CRA and patent notes are informational transparency, not new
obligations EIF is taking on.

**Consequences:** LEGAL.md and TERMS_OF_SERVICE.md bumped to v1.2. No section
was renumbered destructively: new content was folded into existing sections
(Acceptable Use, Hosted Alpha Endpoint, No Warranty, Trademarks) wherever
possible, and only one new section (TOS §9 Miscellaneous) was inserted, to
avoid repeating the cross-reference churn from the v1.1 revision. All four
cross-file section references (PRIVACY_POLICY -> TOS, TOS -> LEGAL x2,
DECISIONS -> LEGAL) reverified correct after the change.

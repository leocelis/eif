# Privacy Policy

> **Version:** 1.1 · **Effective:** 2026-07-19
>
> Short version: **self-hosted EIF collects no data from you, ever.** If you instead
> use the optional hosted alpha endpoint (`eif.leocelis.com`), your claim text is
> processed in memory on the maintainer's server to run the pipeline, is never logged
> or written to disk, and there is still no telemetry, no analytics, and no account
> system beyond a Bearer key. This policy documents both cases and the data flows
> *you* can initiate when you enable optional features.

---

## 1. What the Maintainer Collects

**Self-hosted (`eif-engine` package, `eif-mcp-server` stdio, `eif-mcp-http-server`
local HTTP, the Docker image):** nothing. These transmit no data to the maintainer
under any configuration. There is no phone-home code, no usage metrics endpoint, and
no update check.

**Hosted alpha endpoint (`eif.leocelis.com`, optional, opt-in):** if you use it, your
claim and evidence text is sent to the maintainer's server to run the EIF pipeline.
It is held in memory only for the duration of your session (in-process, TTL 24
hours) and is never written to disk or logged; the only thing the server logs is a
truncated key identifier, the routing verdict, and the evidence tier used (see
`eif/mcp_server/http_server.py`, which is open source). No account system beyond the
Bearer key; no analytics; no usage tracking beyond that log line.

Because no personal data is transmitted to the maintainer through the self-hosted
path, the maintainer is neither a controller nor a processor of your data under the
GDPR for self-hosted use. See §5. If you choose the hosted alpha endpoint, see §5 for
how that changes this analysis.

---

## 2. Data Flows You Can Initiate

Two optional features make outbound network calls. Both go **directly from your
machine to the third party**; the maintainer is not in the path and receives nothing.

- **DuckDuckGo search** (via the `ddgs` library): if you enable web evidence
  collection, claim-derived search queries are sent to DuckDuckGo. DuckDuckGo's own
  privacy policy applies to those queries.
- **OpenAI API**: only if you set `OPENAI_API_KEY`. The critic tournament and the
  causal evidence probe then send claim and evidence text to the OpenAI API under your
  own account. OpenAI's terms and privacy policies apply, including their data-usage
  and retention settings for your account.

Do not enable these features on claims containing personal data, credentials, or
confidential information unless your own arrangements with those providers cover that
transmission.

---

## 3. GitHub

The repository is hosted on GitHub. If you star the repository, open issues, post in
discussions, or submit pull requests, GitHub processes that activity (including your
username and any content you post) under GitHub's own privacy statement. Content you
post in public issues and discussions is public.

---

## 4. Local Artifacts

EIF writes working data to your local machine only:

- Session store and cost ledger under `~/.eif/`
- Provenance records produced by the RECORD phase, written where you configure them

These files never leave your machine unless you move them. You control their
retention, protection, and deletion. If you process personal data through EIF, these
local artifacts may contain it, and securing and erasing them is your responsibility
as the controller of that data.

The local HTTP server (`eif-mcp-http-server`) binds to 127.0.0.1 by default and
optionally requires a single `EIF_API_KEY` bearer token. If you rebind it to a
non-loopback interface, you are exposing an interface that handles your claim data;
secure it accordingly.

---

## 5. GDPR Note

**Self-hosted:** the maintainer does not process personal data on your behalf,
because no data is transmitted to the maintainer. No data processing agreement with
the maintainer is applicable or available. Organizations that deploy EIF's HTTP
server internally and need a DPA between their own entities may use the template in
[DATA_PROCESSING_AGREEMENT.md](DATA_PROCESSING_AGREEMENT.md).

**Hosted alpha endpoint:** using `eif.leocelis.com` does involve a transmission of
your claim text to the maintainer's infrastructure to run the pipeline, in-memory
only and never persisted. Per §1, this is a minimal, non-logged, transient
processing operation for a private alpha. Do not send personal data through the
hosted endpoint (see [TERMS_OF_SERVICE.md](TERMS_OF_SERVICE.md) §7); if you need to
process personal data through EIF, self-host instead, where the "no transmission"
guarantee is categorical.

If your use of EIF involves personal data (in claims, evidence, or local artifacts),
you are the controller for that processing, including any transmission to
DuckDuckGo, OpenAI, or the hosted alpha endpoint that you enable.

---

## 6. Changes

The version and effective date above reflect the last revision. Changes are tracked in
[`CHANGELOG.md`](CHANGELOG.md). Given that the core promise of this policy is "no
collection", any future change introducing a data flow to the maintainer would be a
material change, prominently announced in the repository.

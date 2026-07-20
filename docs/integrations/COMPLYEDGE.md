# ComplyEdge TrustLint - EIF integration

EIF uses [ComplyEdge](https://complyedge.io) TrustLint on LLM-facing artifacts: offline EU AI Act screening, optional runtime checks, and a public trust surface.

**Tenant slug:** `eif`

---

## What runs where

| Layer | Mechanism | API key in repo? | Blocks merge? |
|-------|-----------|------------------|---------------|
| **Offline gate** | `trustlint check` via `./scripts/compliance/check.sh` | No | Yes (CI `compliance` job) |
| **Runtime enforcement** | `POST /v1/check` via `./scripts/compliance/runtime_check.sh` | No (BYOK env only) | No (opt-in, push-to-main) |
| **Public proof** | Live seal + trust JSON | No | N/A |

```
edit eif/**/*_intent.yaml -> check.sh -> CI green
                    v optional BYOK
              runtime_check.sh -> /v1/check -> audit trail -> badge + trust page
```

---

## Public surfaces

| Surface | URL |
|---------|-----|
| Enforcement seal (SVG) | https://api.complyedge.io/v1/public/badge/eif.svg |
| Trust JSON | https://api.complyedge.io/v1/public/trust/eif |
| Trust page | https://trust.complyedge.io/eif |
| Origin site | https://github.com/leocelis/eif |

The seal reflects **live runtime audit data** (checks in 24h / 30d). It is not a static marketing badge.

---

## LLM-facing scan scope

| Path | Role |
|------|------|
| `eif/**/*_intent.yaml` (14 files) | IVD-style intent artifacts - constraints the engine's design was built against |

Scope is set in `.trustlint.yaml` and mirrored in `scripts/compliance/check.sh`'s `find` target.

---

## Operator setup (BYOK)

1. Provision a ComplyEdge tenant with slug `eif` and store the API key in env only: `COMPLYEDGE_API_KEY` (GitHub Actions secret for the optional runtime job, never in git).
2. Enable public trust:

```bash
curl -s -X PATCH https://api.complyedge.io/v1/tenant/trust \
  -H "Authorization: Bearer $COMPLYEDGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"trust_public_enabled": true, "public_slug": "eif", "display_name": "EIF - Epistemic Integrity Framework", "website_url": "https://github.com/leocelis/eif"}'
```

3. Seed runtime checks (feeds the live seal):

```bash
export COMPLYEDGE_API_KEY=ce_...
./scripts/compliance/runtime_check.sh
```

---

## CI

| Job | Path | Secret required |
|-----|------|-----------------|
| `test` | `pytest` (3.11, 3.12 matrix) | None |
| `lint` | `ruff check` | None |
| `compliance` | `./scripts/compliance/check.sh` | None |
| `compliance-runtime` (optional) | `./scripts/compliance/runtime_check.sh` | `COMPLYEDGE_API_KEY` |

Offline gate is the auditable merge blocker. Runtime is opt-in proof for live trust metrics; it runs only on push to `main` and skips cleanly when the secret is absent.

---

## Local validation

```bash
pip install 'trustlint>=2.0.1'
./scripts/compliance/check.sh
export COMPLYEDGE_API_KEY=ce_...
./scripts/compliance/runtime_check.sh
```

---

## References

- Offline gate script: `scripts/compliance/check.sh`
- Runtime probe script: `scripts/compliance/runtime_check.sh`
- TrustLint config: `.trustlint.yaml`
- CE OSS adoption guide: `complyedge-platform/docs/development/oss-trustlint-adoption-guide.md`
- Same pattern: [leocelis/ivd](https://github.com/leocelis/ivd), [leocelis/horizon](https://github.com/leocelis/horizon)

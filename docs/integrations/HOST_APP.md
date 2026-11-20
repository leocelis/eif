# Host apps: one EIF server for many tenants

> Needs a release after 4.2.0. Tenant keys are on `main`, not yet on PyPI.

A **host app** is an application that serves many of its own customers
(tenants) and wants to give each of them claim verification through one
self-hosted EIF HTTP server (`eif-mcp-http-server`).

The host and the server share one secret. The host derives a key for each
tenant on demand; the server recomputes it. There is no provisioning step and
neither side stores a key. Each tenant's sessions are visible only to that
tenant.

`EIF_API_KEY` (the operator key) keeps working exactly as before, next to
tenant keys.

## 1. Server settings

| Variable | Meaning | Default |
|---|---|---|
| `EIF_TENANT_KEY_SECRET` | The shared secret. Not set: tenant keys are off | not set |
| `EIF_TENANT_KEY_VERSIONS` | Comma-separated versions the server accepts | `v1` |
| `EIF_REVOKED_TENANTS` | Comma-separated tenants whose keys are refused | empty |
| `EIF_API_KEY` | Optional operator key (all tools, ownerless sessions) | not set |

With `EIF_TENANT_KEY_SECRET` set and `EIF_API_KEY` unset, the server accepts
tenant keys only, in development and in production.

## 2. Deriving a tenant key

```
key = "eif_" + tenant + "_" + base64url_nopad( HMAC-SHA256(SECRET, "eif:" + VERSION + ":" + tenant) )
```

- `tenant` matches `^[a-z0-9][a-z0-9-]{0,55}$`, lowercase only. Map your own
  tenant ids to this form once and keep the mapping stable.
- The MAC is always 43 characters. The server reads the tenant as the text
  between `eif_` and the last 44 characters; never split the key on `_` (the
  MAC can contain `_`).
- `VERSION` is one of `EIF_TENANT_KEY_VERSIONS`, normally `v1`.
- The signed text starts with `eif:`, so a key made for another product is not
  valid here even if the same secret is reused.

Python:

```python
import base64, hashlib, hmac

def eif_tenant_key(secret: str, tenant: str, version: str = "v1") -> str:
    mac = hmac.new(secret.encode(), f"eif:{version}:{tenant}".encode(), hashlib.sha256).digest()
    return f"eif_{tenant}_" + base64.urlsafe_b64encode(mac).rstrip(b"=").decode()
```

The same function ships as `eif.mcp_server.auth.make_tenant_key(secret, tenant, version)`.

Test vector (check your implementation against it):

| Secret | Version | Tenant | Key |
|---|---|---|---|
| `test-secret-do-not-use` | `v1` | `acme` | `eif_acme_Zz3YW-iyGIXp3c4AL9D0Kcpxxyneizso6QEKw0_Lf9I` |

Send the key as `Authorization: Bearer <key>` on MCP requests (`/mcp`, `/sse`),
or as `"api_key"` in the JSON body of `POST /verify`.

## 3. What a tenant can do

| Allowed | Refused |
|---|---|
| `eif_new_session`, `eif_extract_claims_from_decision`, `eif_verify` | Every other tool |

`tools/list` for a tenant key returns only these three. Tools that can call a
paid model on the server operator's key (`eif_challenge`, the causal evidence
probe) are out of tenant reach. `eif_get_session` is not offered: it reports
only the provenance chain, which tenants do not write. The verdict comes back
from `eif_verify` itself.

The five session resources (`eif://session/{id}/…`) are readable for the
tenant's own sessions.

## 4. Isolation rules

- **A session has an owner**: the tenant of the request that created it. Any
  other tenant asking for it, by tool or by resource, gets the same "not found
  or expired" error as for an id that does not exist.
- A session created with `EIF_API_KEY` is not readable with a tenant key, and
  the reverse.
- **One MCP session, one key.** An MCP session is bound to the key that opened
  it. A message on that MCP session with another tenant's key (or the operator
  key) is refused. Open one MCP session per tenant.
- `POST /verify` with a tenant key creates a session owned by that tenant.

## 5. Rotation and revocation

- Rotate: add a version (`EIF_TENANT_KEY_VERSIONS=v1,v2`), move the host to
  derive with `v2`, then remove `v1`.
- Revoke one tenant at once: add it to `EIF_REVOKED_TENANTS`.
- Replacing `EIF_TENANT_KEY_SECRET` invalidates every tenant key.

## 6. What a host should send

The server works best when the host, not the model, fills two arguments of
`eif_verify`:

- `conversation_turns`: the recent turns, as `{"role": "user"|"assistant",
  "content": str}`. Without them the sycophancy check reports
  "SKIPPED - no conversation context".
- `host_tool_outputs`: data the host already fetched (database rows, API
  results), as `{"tool_name", "query", "result", "data_scope"}`. It is the
  strongest evidence tier, and it only means something when the host supplies
  it, not when the model writes it.

## 7. Limits

- Sessions live in memory. A server restart loses them for every caller; the
  host opens a new session and retries.
- Rate limits (`EIF_RATE_LIMIT_PER_MINUTE`) are per key and per process.
- Terminate TLS in front of the server and keep the secret out of source
  control (see `SECURITY.md`).

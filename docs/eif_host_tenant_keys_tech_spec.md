# EIF: Host-Derived Tenant Keys and Session Owners: Tech Spec

**Status:** PROPOSED (2026-11-15). Not built.
**Scope:** the self-hosted HTTP server (`eif/mcp_server/`) and the session store (`eif/session.py`).
Stdio and local use do not change.

## 1. Problem

The HTTP server has one shared key, `EIF_API_KEY` (`eif/mcp_server/auth.py`). Its own note says:
"For multi-user deployments, put a real gateway in front." Sessions live in one in-memory dict with
no owner (`eif/session.py`): anyone who holds a `session_id` can read that session.

That fits one person. It does not fit a **host app** that serves many of its own customers
(tenants) through one EIF server: every tenant would share one key, and a leaked session id would
open another tenant's claims and evidence.

## 2. Goal

A host app can give each of its tenants claim verification, with one secret shared between the host
and the server, no provisioning step, and no tenant able to read another's session.

The existing `EIF_API_KEY` keeps working exactly as today.

## 3. Design

### 3.1 The key

```
key = "eif_" + tenant + "_" + base64url_nopad( HMAC-SHA256(SECRET, "eif:" + VERSION + ":" + tenant) )
```

- `tenant` matches `^[a-z0-9][a-z0-9-]{0,55}$`. Lowercase only.
- The MAC is always 43 characters. The server reads the tenant as the text between the prefix and
  the last 44 characters, never by splitting on `_`.
- Neither the host nor the server stores the key.
- The signed text starts with the product name, so a key made for one server is not valid on
  another even if an operator reuses a secret.

Test vector (each project that implements this scheme carries its own, same secret and tenant):

| Secret | Version | Tenant | Key |
|---|---|---|---|
| `test-secret-do-not-use` | `v1` | `acme` | `eif_acme_Zz3YW-iyGIXp3c4AL9D0Kcpxxyneizso6QEKw0_Lf9I` |

### 3.2 Server settings

| Variable | Meaning | Default |
|---|---|---|
| `EIF_TENANT_KEY_SECRET` | The shared secret. Not set → the feature is off | not set |
| `EIF_TENANT_KEY_VERSIONS` | Comma-separated versions the server accepts | `v1` |
| `EIF_REVOKED_TENANTS` | Comma-separated tenants whose keys are refused | empty |

### 3.3 Verification (E1)

`validate_key` accepts a bearer key that is not `EIF_API_KEY` when the secret is set, the key has the
`eif_` prefix and a valid tenant, its MAC matches for an accepted version (constant-time compare),
and the tenant is not revoked. Its `key_info` gains `tenant`.

A request made with `EIF_API_KEY` has no tenant.

Three things in today's code need care:

- **Order.** With `EIF_API_KEY` unset outside production, `validate_key` accepts any key as a local
  developer before anything else is checked; in production it rejects everything. When the tenant
  secret is set, the tenant check runs first, and a server with a tenant secret and no
  `EIF_API_KEY` serves tenant keys only.
- **The middleware discards the result today** (`http_server.py` calls `require_api_key` and drops
  what it returns). It keeps it.
- **`POST /verify`** is a second way in: it reads the key from the JSON body and opens a session
  itself. It attaches the same tenant and owner as the MCP path.

The tenant is read from **each message's own request**, not from a value set when the MCP
session was opened. With stateful Streamable HTTP the server task for a session starts inside the
request that created it, so a per-request variable set there stays the first caller's. A session is
also bound to the identity that opened it: a message whose key resolves to a different identity
(another tenant, or an operator key) is refused. Without that, one MCP session reused for two
tenants would run both as the first.
The compliance module already reads the message's own request this way (`compliance.py`,
`_request_identity`).

### 3.4 A session has an owner (E2)

- `new_session` records the tenant of the request that created it (none for `EIF_API_KEY`).
- `get_session` and `update_session` take the caller's tenant. A session asked for by a different
  tenant raises the same "not found or expired" error as a session that does not exist, so the
  answer does not reveal that the id is real.
- The same check applies to the five session resources (`eif://session/{id}/…`).
- A session with no owner is readable only by callers with no tenant, as today.

### 3.5 What a tenant key may call (E3)

| Allowed | Refused |
|---|---|
| `eif_new_session`, `eif_extract_claims_from_decision`, `eif_verify` | Every other tool |

`eif_challenge` and the causal evidence probe call OpenAI on the server operator's key. They stay
out of tenant reach so a tenant cannot spend the operator's money. `tools/list` for a tenant key
returns only the three allowed tools.

`eif_get_session` is left out on purpose: it reports only the provenance chain, which only
`eif_record` writes, and `eif_record` is not offered. A tenant would always read an empty session.
The verdict a tenant needs comes back from `eif_verify` itself.

### 3.6 What a host should send

The server works best when the host, not the model, fills two arguments of `eif_verify`:

- `conversation_turns`: without them the sycophancy check reports "SKIPPED - no conversation
  context".
- `host_tool_outputs`: data the host already fetched. It is the strongest evidence tier, and it
  only means something when the host supplies it.

## 4. What does not change

- `EIF_API_KEY`: same tools, same sessions.
- Stdio transport and local development mode.
- Sessions stay in memory. A restart loses them for every caller; a host opens a new one and
  retries.

## 5. Tests

- The test vector verifies; a tampered MAC, an unknown version, a revoked tenant and a tenant that
  breaks the rule are refused.
- Tenant B asking for tenant A's session, by tool or by resource, gets "not found or expired".
- A session created with `EIF_API_KEY` is not readable with a tenant key, and the reverse.
- A tenant key calling `eif_challenge` is refused; `tools/list` shows three tools.
- With the tenant secret set and `EIF_API_KEY` unset, in development and in production, a valid
  tenant key is accepted and a tampered one is refused.
- `POST /verify` with a tenant key creates a session owned by that tenant.
- An MCP session opened with one key and continued with another is refused.
- `EIF_API_KEY` behaves as before.

## 6. Files

`eif/mcp_server/auth.py`, `eif/mcp_server/http_server.py`, `eif/mcp_server/server.py`,
`eif/mcp_server/resources.py`, `eif/session.py`, `SECURITY.md`, a new
`docs/integrations/HOST_APP.md`, tests. `docs/architecture.md` gains one paragraph under
"MCP surface" once this is built.

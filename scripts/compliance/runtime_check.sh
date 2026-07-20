#!/usr/bin/env bash
# scripts/compliance/runtime_check.sh
#
# Optional maintainer-side runtime compliance probe - POST /v1/check against
# the ComplyEdge API. Requires a ComplyEdge API key; contributors can ignore
# this script (CI skips it when no key is configured).
#
# Usage (from repo root):
#   export COMPLYEDGE_API_KEY=ce_live_...   # never commit
#   ./scripts/compliance/runtime_check.sh
#
# Optional:
#   COMPLYEDGE_AGENT_ID=eif-agent  (default)
#   COMPLYEDGE_API_URL=https://api.complyedge.io
#
# Exit codes:
#   0 - allowed (no blocking violations)
#   1 - blocked by runtime enforcement
#   2 - missing key or transport error

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

API_URL="${COMPLYEDGE_API_URL:-https://api.complyedge.io}"
AGENT_ID="${COMPLYEDGE_AGENT_ID:-eif-agent}"
PROBE_TEXT="${COMPLYEDGE_RUNTIME_PROBE_TEXT:-EIF runtime compliance probe - EU check on representative LLM-facing artifact text.}"

if [ -z "${COMPLYEDGE_API_KEY:-}" ]; then
  echo "ERROR: COMPLYEDGE_API_KEY not set (BYOK - env only, never commit)." >&2
  exit 2
fi

payload=$(PROBE_TEXT="$PROBE_TEXT" AGENT_ID="$AGENT_ID" python3 -c "
import json, os
print(json.dumps({
    'text': os.environ['PROBE_TEXT'],
    'agent_id': os.environ['AGENT_ID'],
    'jurisdiction': 'EU',
    'direction': 'output',
}))
")

response=$(curl -sS -w "\n%{http_code}" -X POST "${API_URL%/}/v1/check" \
  -H "Authorization: Bearer ${COMPLYEDGE_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$payload")

http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" != "200" ]; then
  echo "ERROR: /v1/check returned HTTP ${http_code}" >&2
  echo "$body" >&2
  exit 2
fi

allowed=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('allowed') else 'false')")
violations=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('violations') or []))")
latency=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('latency_ms', 0))")

if [ "$allowed" = "true" ]; then
  echo "ComplyEdge runtime OK - allowed (${latency}ms, ${violations} violation(s))"
  exit 0
fi

echo "ComplyEdge runtime BLOCKED - ${violations} violation(s) (${latency}ms)" >&2
echo "$body" >&2
exit 1

#!/usr/bin/env bash
# scripts/compliance/check.sh
#
# Offline TrustLint compliance gate for EIF LLM-facing artifacts.
#
# Usage (from repo root):
#   ./scripts/compliance/check.sh
#
# Requires: pip install 'trustlint>=2.0.1'
# Rules: downloaded from public ComplyEdge/complyedge release (see bootstrap_rules).
# No COMPLYEDGE_API_KEY - offline Tier 1 regex only.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

JURISDICTION="${TRUSTLINT_JURISDICTION:-EU}"
RULES_HOME="${HOME}/.trustlint/rules"
RULES_CACHE="${REPO_ROOT}/.trustlint-cache/rules"
RULES_DIR=""

if ! command -v trustlint >/dev/null 2>&1; then
  echo "ERROR: trustlint not found. Install: pip install 'trustlint>=2.0.1'" >&2
  exit 2
fi

bootstrap_rules() {
  if [ -n "${TRUSTLINT_RULES_DIR:-}" ] && [ -d "$TRUSTLINT_RULES_DIR" ]; then
    RULES_DIR="$TRUSTLINT_RULES_DIR"
    return
  fi
  if [ -d "$RULES_HOME" ] && find "$RULES_HOME" -name '*.yaml' -print -quit 2>/dev/null | grep -q .; then
    RULES_DIR="$RULES_HOME"
    return
  fi
  if [ -d "$RULES_CACHE" ] && find "$RULES_CACHE" -name '*.yaml' -print -quit 2>/dev/null | grep -q .; then
    RULES_DIR="$RULES_CACHE"
    return
  fi

  echo "TrustLint rules missing - downloading from ComplyEdge/complyedge public release..." >&2
  python3 - <<'PY'
import json
import os
import tarfile
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

repo = "ComplyEdge/complyedge"
cache = Path(os.environ["RULES_CACHE"])
token = os.environ.get("GITHUB_TOKEN", "")

headers = {"User-Agent": "eif-trustlint-bootstrap"}
if token:
    headers["Authorization"] = f"Bearer {token}"

api = f"https://api.github.com/repos/{repo}/releases/latest"
with urlopen(Request(api, headers=headers), timeout=30) as resp:
    release = json.loads(resp.read().decode())
tag = release.get("tag_name", "unknown")
tarball_url = release.get("tarball_url")
if not tarball_url:
    raise SystemExit("No tarball_url in latest ComplyEdge/complyedge release")

with urlopen(Request(tarball_url, headers=headers), timeout=120) as resp:
    data = resp.read()

with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
    tmp.write(data)
    tar_path = tmp.name

cache.mkdir(parents=True, exist_ok=True)
count = 0
with tarfile.open(tar_path, "r:gz") as tar:
    for member in tar.getmembers():
        if "/rules/regulations/" in member.name and member.name.endswith(".yaml"):
            rel = member.name.split("/rules/regulations/", 1)[1]
            dest = cache / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(member)
            if src:
                dest.write_bytes(src.read())
                count += 1

Path(tar_path).unlink(missing_ok=True)
if count == 0:
    raise SystemExit(f"No rules extracted from release {tag}")
print(f"Downloaded {count} rules from {tag} to {cache}")
PY

  RULES_DIR="$RULES_CACHE"
}

export RULES_CACHE
bootstrap_rules

probe_out="$(trustlint --rules-dir "$RULES_DIR" check --text "compliance probe" -j "$JURISDICTION" 2>&1)" || true
if echo "$probe_out" | grep -q "No rules loaded"; then
  echo "ERROR: TrustLint rules not loaded from $RULES_DIR" >&2
  exit 2
fi

checked=0
failed=0

check_file() {
  local f="$1"
  [ -f "$f" ] || return 0
  checked=$((checked + 1))
  if ! trustlint --rules-dir "$RULES_DIR" check "$f" -j "$JURISDICTION"; then
    echo "FAIL: $f" >&2
    failed=$((failed + 1))
  fi
}

should_skip() {
  local f="$1"
  case "$f" in
    */.venv/*|*/__pycache__/*|*/.git/*|*/.trustlint-cache/*) return 0 ;;
  esac
  return 1
}

while IFS= read -r -d '' f; do
  should_skip "$f" && continue
  check_file "$f"
done < <(find eif -type f -name '*_intent.yaml' -print0 2>/dev/null || true)

if [ "$failed" -gt 0 ]; then
  echo "TrustLint compliance check failed ($failed file(s))." >&2
  exit 1
fi

echo "TrustLint OK - $checked file(s) scanned (jurisdiction: $JURISDICTION)"

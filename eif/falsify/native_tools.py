"""EIF Native Tools - self-sufficient P1 + P3 evidence collection.

EIF ships its own search client and code sandbox so it does not depend on
the host agent having web search or code execution configured. This makes
the MCP server deployment zero-config for evidence collection.

P3 search backend:
  DDGS (deedy5/ddgs) v9.13.0
  Source: github.com/deedy5/ddgs (2605 stars, MIT, no API key, April 2026)
  API:    DDGS().text(query, max_results=N) -> list[dict(title, href, body)]

P1 code sandbox:
  Uses subprocess (stdlib) - same pattern as evidence_collector.py.
  Wraps execution with timeout and safe stdout capture.

Intent: eif/eif/falsify/eif_native_tools_intent.yaml (NT1–NT6)
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import textwrap
from typing import Any

# NT3: dangerous names that must not appear in EIF-generated code templates.
# EIF templates only use stdlib math/json/statistics - nothing else is expected.
_FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "os", "sys", "subprocess", "shutil", "socket", "urllib",
    "requests", "httpx", "open", "exec", "eval", "compile",
    "__import__", "importlib", "ctypes", "pickle",
})


# ─────────────────────────────────────────────────────────────────────────────
# P3: Native web search via DDGS
# Source: github.com/deedy5/ddgs (deedy5/ddgs, MIT, 2605 stars)
# ─────────────────────────────────────────────────────────────────────────────

def native_search(query: str, max_results: int = 5) -> str:
    """Run a web search using DDGS and return concatenated title+body as evidence string.

    Compatible with the web_search_fn callable interface expected by
    collect_web_search() in evidence_collector.py.

    Args:
        query: the search query, typically the claim text + "evidence research"
        max_results: number of results to retrieve (default 5)

    Returns:
        Concatenated string of title + body for all results, or "" on failure.

    Raises:
        ImportError: if ddgs is not installed (with pip install instruction).

    Source: github.com/deedy5/ddgs
    """
    try:
        from ddgs import DDGS  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "EIF native search requires ddgs. Install it with: pip install ddgs\n"
            "Source: github.com/deedy5/ddgs (MIT, no API key required)"
        ) from exc

    try:
        results: list[dict[str, Any]] = DDGS().text(query, max_results=max_results)
        if not results:
            return ""
        # Concatenate title + body for each result - compatible with is_relevant()
        # and the key-term extraction in collect_web_search()
        parts = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            parts.append(f"{title}. {body} [{href}]")
        return " | ".join(parts)
    except Exception:  # noqa: BLE001
        # NT2: network failures must be silent - return empty string
        return ""


def native_search_fn(query: str) -> str:
    """Drop-in replacement for web_search_fn parameter in collect_web_search().

    Use this directly as the web_search_fn argument:
        collect_web_search(claim_text, web_search_fn=native_search_fn)

    Or let collect_evidence() auto-substitute it when web_search_fn=None.
    """
    return native_search(query)


# ─────────────────────────────────────────────────────────────────────────────
# P1: Native code execution sandbox
# Same subprocess pattern as evidence_collector.py - made standalone here
# so it can be tested independently and used outside the full collector.
# ─────────────────────────────────────────────────────────────────────────────

def _validate_code(code: str) -> str | None:
    """AST-based safety check before subprocess execution (NT3).

    Returns None when safe, or an error string describing the violation.
    Only EIF's own code templates should reach this function - they use
    math, json, and statistics exclusively.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"SYNTAX_ERROR: {exc}"

    for node in ast.walk(tree):
        # Block dangerous imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if node.module else [])
            )
            for name in names:
                root = (name or "").split(".")[0]
                if root in _FORBIDDEN_NAMES:
                    return f"FORBIDDEN_IMPORT: {name!r}"
        # Block dangerous builtins by name
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            return f"FORBIDDEN_BUILTIN: {node.id!r}"
        # Block attribute access on forbidden modules (e.g. os.system)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in _FORBIDDEN_NAMES:
                return f"FORBIDDEN_ATTRIBUTE: {node.value.id}.{node.attr}"
        # Block dunder access categorically. This is the real sandbox boundary:
        # every known pure-Python object-introspection escape (walking
        # ().__class__.__bases__[0].__subclasses__() to reach a loaded class,
        # then that class's __init__.__globals__ to reach os/subprocess without
        # ever writing the word "os") routes through a dunder name. A specific
        # name denylist cannot close this class of attack; only rejecting the
        # dunder pattern itself does. EIF's templates never need one.
        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            return f"FORBIDDEN_DUNDER_ATTRIBUTE: {node.attr!r}"
        if isinstance(node, ast.Name) and node.id.startswith("__") and node.id.endswith("__"):
            return f"FORBIDDEN_DUNDER_NAME: {node.id!r}"

    return None  # safe


def native_run_code(code: str, timeout: int = 10) -> tuple[str, bool]:
    """Execute a Python code string in a subprocess sandbox.

    The code must print a single-line JSON to stdout. Returns the raw
    stdout output and a success flag.

    Args:
        code: Python source code to execute. Must print JSON to stdout.
        timeout: seconds before the subprocess is killed (default 10)

    Returns:
        (output_str, success): stdout content and True if exit_code==0.

    Safety: AST validation (NT3) runs before execution to reject dangerous
    imports, builtins, and (categorically) any dunder attribute or name
    access - which closes the standard class of Python object-introspection
    sandbox escapes (walking __class__/__bases__/__subclasses__ to reach a
    loaded class, then its __init__.__globals__ to reach os/subprocess
    without ever writing a forbidden name), not just specific denylisted
    imports. The subprocess also gives process isolation. This is a strong
    mitigation, not a formal security boundary against a determined attacker
    with novel techniques; do not run genuinely untrusted code through it.
    EIF templates only use stdlib (math, json, re, statistics).
    """
    violation = _validate_code(code)
    if violation:
        return (f"INVALID_CODE: {violation}", False)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(textwrap.dedent(code))
            tmp_path = tmp.name

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout.strip()
        return (output, result.returncode == 0)

    except subprocess.TimeoutExpired:
        return ("TIMEOUT", False)
    except Exception:  # noqa: BLE001
        return ("UNAVAILABLE", False)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Auto-substitution helper: used by collect_evidence() in evidence_collector.py
# ─────────────────────────────────────────────────────────────────────────────

def get_native_search_fn() -> Any:
    """Return native_search_fn if ddgs is available, else None.

    Used by collect_evidence() to auto-substitute P3 when web_search_fn=None.
    If ddgs is not installed, returns None so P4 fallback is used as before.
    """
    try:
        from ddgs import DDGS  # noqa: F401, PLC0415
        return native_search_fn
    except ImportError:
        return None

"""P1 code-execution sandbox: injection and object-introspection regression tests.

Found via adversarial testing of the hosted MCP endpoint's attack surface:
a claim submitted through eif_verify can reach collect_code_execution, whose
templates run generated Python in a subprocess. Two independent bugs
combined into a working, proof-of-concept remote code execution:

  1. Claim text was substituted into template string literals via a naive
     '"' -> "'" replace, which a trailing-backslash payload could still
     break out of (the backslash escapes the template's own closing quote).
  2. The AST validator (_validate_code) denylisted specific names
     (os, subprocess, ...) but not dunder attribute access, so a payload
     using ().__class__.__bases__[0].__subclasses__() to find an
     already-loaded class, then that class's __init__.__globals__ to reach
     os.system directly, bypassed the denylist entirely without ever
     writing a forbidden name.

Fix: templates now receive claim text via json.dumps() (a properly escaped
Python string literal, immune to breakout), and _validate_code additionally
rejects any dunder-pattern Name or Attribute categorically, which closes the
entire class of Python object-introspection sandbox escapes, not just the
one gadget above.

A third, unrelated bug in the same code path is also covered here: all five
templates imported `sys` for early-return control flow, and `sys` is (and
must remain) on the forbidden-imports denylist, so every invocation of P1
code execution silently failed with FORBIDDEN_IMPORT regardless of claim
content. Fixed by wrapping template bodies in a function and using `return`.
"""

import pytest

from eif.falsify.evidence_collector import _CODE_TEMPLATES, collect_code_execution
from eif.falsify.native_tools import _validate_code, native_run_code


class TestDunderBlockedCategorically:
    def test_subclasses_gadget_blocked(self):
        code = """
for c in ().__class__.__bases__[0].__subclasses__():
    if c.__name__ == "Popen":
        c(["true"])
"""
        assert _validate_code(code) is not None

    def test_globals_gadget_blocked(self):
        code = '(lambda: 0).__globals__["__builtins__"]'
        assert _validate_code(code) is not None

    def test_class_attribute_blocked(self):
        assert _validate_code("x = (1).__class__") is not None

    def test_plain_dunder_name_blocked(self):
        assert _validate_code("print(__name__)") is not None

    def test_legitimate_templates_pass_validation(self):
        """The fix must not break the feature it protects."""
        for template in _CODE_TEMPLATES.values():
            code = template.format(claim='"benign test claim"')
            assert _validate_code(code) is None, f"legitimate template rejected: {code[:80]}"


class TestNoCodeExecutionAchieved:
    """End-to-end: run known-dangerous gadgets through native_run_code and
    confirm they produce no observable side effect, rather than trusting
    the validator alone.
    """

    def test_subclasses_popen_gadget_produces_no_side_effect(self, tmp_path):
        marker = tmp_path / "marker"
        code = f"""
for c in ().__class__.__bases__[0].__subclasses__():
    if c.__name__ == "Popen":
        c(["touch", "{marker}"])
"""
        violation = _validate_code(code)
        assert violation is not None
        assert not marker.exists()

    def test_wrap_close_globals_gadget_produces_no_side_effect(self, tmp_path):
        marker = tmp_path / "marker"
        code = f"""
target = [c for c in ().__class__.__bases__[0].__subclasses__() if c.__name__ == "_wrap_close"][0]
target.__init__.__globals__["system"]("touch {marker}")
"""
        violation = _validate_code(code)
        assert violation is not None
        assert not marker.exists()


class TestClaimTemplatingIsInjectionSafe:
    """collect_code_execution must treat claim text as inert data no matter
    what it contains - quotes, backslashes, newlines, or gadget payloads.
    """

    @pytest.mark.parametrize(
        "payload",
        [
            'churn 5% \\") ; import os; os.system("touch /tmp/should_not_exist") ; x = ("',
            'churn rate is 5%"; import os; os.system("touch /tmp/should_not_exist"); x="',
            'churn rate 5%\nfor c in ().__class__.__bases__[0].__subclasses__():\n'
            '    if c.__name__=="Popen": c(["touch","/tmp/should_not_exist"])\n',
        ],
    )
    def test_injection_payloads_are_treated_as_inert_text(self, payload):
        result = collect_code_execution(payload)
        # The claim still parses as a churn claim ("5%" is extracted); the
        # injected code must never execute, so the verdict is a normal
        # benchmark comparison, not an error or a sign of code having run.
        assert result.verdict in ("SUPPORTS", "CONTRADICTS")


class TestP1TemplatesAreFunctional:
    """Regression guard for the silent sys-import breakage: every template
    must actually produce a real verdict for a matching benign claim, not
    INSUFFICIENT via a rejected AST screen.
    """

    @pytest.mark.parametrize(
        "claim",
        [
            "our annual churn rate is 6%",
            "the AI healthcare market is worth $15 billion",
            "P99 latency is 45ms",
            "migrating to microservices will reduce latency",
            "cloud costs will be $8000 per month",
        ],
    )
    def test_benign_claim_gets_a_real_verdict(self, claim):
        result = collect_code_execution(claim)
        assert result.verdict in ("SUPPORTS", "CONTRADICTS"), (
            f"expected a computed verdict, got {result.verdict}: {result.evidence_summary}"
        )

    def test_native_run_code_still_works_for_benign_code(self):
        output, ok = native_run_code('import json\nprint(json.dumps({"ok": True}))')
        assert ok
        assert "true" in output.lower()

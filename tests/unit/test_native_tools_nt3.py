"""Tests for NT3: AST safety validation in native_run_code() (native_tools.py).

Intent: eif_native_tools_intent.yaml NT3 - validates code template before execution.
"""

from __future__ import annotations

from eif.falsify.native_tools import _validate_code, native_run_code


class TestValidateCode:
    """_validate_code() rejects dangerous code; passes safe templates."""

    def test_safe_math_code_passes(self) -> None:
        code = "import json, math\nprint(json.dumps({'verdict': 'PASS', 'value': math.pi}))"
        assert _validate_code(code) is None

    def test_safe_statistics_code_passes(self) -> None:
        code = "import statistics, json\ndata=[1,2,3]\nprint(json.dumps({'mean': statistics.mean(data)}))"
        assert _validate_code(code) is None

    def test_forbidden_os_import_rejected(self) -> None:
        code = "import os\nos.system('ls')"
        result = _validate_code(code)
        assert result is not None
        assert "os" in result

    def test_forbidden_subprocess_import_rejected(self) -> None:
        code = "import subprocess\nsubprocess.run(['ls'])"
        result = _validate_code(code)
        assert result is not None
        assert "subprocess" in result

    def test_forbidden_eval_rejected(self) -> None:
        code = "eval('1+1')"
        result = _validate_code(code)
        assert result is not None
        assert "eval" in result

    def test_forbidden_exec_rejected(self) -> None:
        code = "exec('x=1')"
        result = _validate_code(code)
        assert result is not None
        assert "exec" in result

    def test_syntax_error_caught(self) -> None:
        code = "def foo(\n  broken syntax !!!"
        result = _validate_code(code)
        assert result is not None
        assert "SYNTAX_ERROR" in result

    def test_empty_code_passes(self) -> None:
        assert _validate_code("") is None


class TestNativeRunCodeNT3:
    """native_run_code() rejects forbidden code before subprocess."""

    def test_dangerous_code_returns_false(self) -> None:
        code = "import os\nprint(os.getcwd())"
        output, success = native_run_code(code)
        assert success is False
        assert "INVALID_CODE" in output

    def test_valid_code_executes(self) -> None:
        code = "import json\nprint(json.dumps({'verdict': 'PASS'}))"
        output, success = native_run_code(code)
        assert success is True
        assert "verdict" in output

    def test_syntax_error_returns_false(self) -> None:
        code = "def broken("
        output, success = native_run_code(code)
        assert success is False

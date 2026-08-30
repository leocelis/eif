"""D9 tests for composed NIST AI RMF bind (provenance is load-bearing)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_BIND = Path(__file__).resolve().parent / "bind.py"
_EXPECTED_URI = 'https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf'


def _load():
    spec = importlib.util.spec_from_file_location("composed_bind", _BIND)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load bind: {_BIND}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bind_returns_nist_uri():
    bound = _load().bind_unit()
    assert bound["provenance_uri"] == _EXPECTED_URI
    assert bound["provenance_uri"].startswith("https://")


def test_empty_provenance_raises(monkeypatch):
    """Regression: empty URI was the defect; bind must keep refusing it."""
    mod = _load()
    monkeypatch.setattr(mod, "PROVENANCE_URI", "")
    with pytest.raises(ValueError, match="provenance"):
        mod.bind_unit()

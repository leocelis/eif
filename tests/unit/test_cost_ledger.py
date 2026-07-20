"""Unit tests for the cost ledger persistence layer.

Regression coverage for the hosted-server failure where eif_verify crashed
with "[Errno 2] No such file or directory: '.../.eif/cost_ledger.tmp'" because
_save() wrote into a parent directory that did not exist in the container.
Every other ~/.eif writer creates its parent; the ledger must too.
"""

from __future__ import annotations

from eif.cost_model.cost_ledger import CostLedger


def test_save_creates_missing_parent_directory(tmp_path):
    # Point the ledger at a path two levels below a directory that does not
    # exist yet - exactly the fresh-container condition.
    ledger_path = tmp_path / "does" / "not" / "exist" / "cost_ledger.json"
    assert not ledger_path.parent.exists()

    ledger = CostLedger(path=ledger_path)
    summary = ledger.record_halt("claim-key", expected_cost=1000.0)

    assert ledger_path.exists()
    assert summary["total_expected"] == 1000.0


def test_record_halt_accumulates(tmp_path):
    ledger = CostLedger(path=tmp_path / ".eif" / "cost_ledger.json")
    ledger.record_halt("k", 1000.0)
    summary = ledger.record_halt("k", 500.0)
    assert summary["total_expected"] == 1500.0

"""Tests for EvoScientist cross-session strategy memory (eif.memory.strategy)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eif.memory.strategy import StrategyMemory


@pytest.fixture
def tmp_memory(tmp_path: Path) -> StrategyMemory:
    """Return a StrategyMemory backed by a temp file - no state leaks."""
    return StrategyMemory(path=tmp_path / "test_memory.json")


class TestStrategyMemoryRecord:
    """record_session persists outcomes and updates running statistics."""

    def test_record_increments_sessions_seen(self, tmp_memory: StrategyMemory) -> None:
        tmp_memory.record_session(domain="healthcare", final_route="ACT")
        tmp_memory.record_session(domain="healthcare", final_route="ACT")
        data = tmp_memory._data["healthcare"]
        assert data["sessions_seen"] == 2

    def test_halt_count_tracked(self, tmp_memory: StrategyMemory) -> None:
        tmp_memory.record_session(domain="finance", final_route="HALT")
        tmp_memory.record_session(domain="finance", final_route="ACT")
        data = tmp_memory._data["finance"]
        assert data["halt_count"] == 1
        assert abs(data["halt_rate"] - 0.5) < 1e-6

    def test_avg_final_posterior_computed(self, tmp_memory: StrategyMemory) -> None:
        tmp_memory.record_session(domain="legal", final_route="ACT", final_posterior=0.4)
        tmp_memory.record_session(domain="legal", final_route="ACT", final_posterior=0.6)
        data = tmp_memory._data["legal"]
        assert abs(data["avg_final_posterior"] - 0.5) < 1e-6

    def test_evidence_tier_hits_recorded(self, tmp_memory: StrategyMemory) -> None:
        tmp_memory.record_session(domain="generic", final_route="ACT", decisive_tier="P3")
        tmp_memory.record_session(domain="generic", final_route="ACT", decisive_tier="P3")
        data = tmp_memory._data["generic"]
        assert data["evidence_tier_hits"]["P3"] == 2

    def test_paradigm_alerts_tracked(self, tmp_memory: StrategyMemory) -> None:
        tmp_memory.record_session(domain="engineering", final_route="HALT", paradigm_alert=True)
        tmp_memory.record_session(domain="engineering", final_route="ACT", paradigm_alert=False)
        data = tmp_memory._data["engineering"]
        assert data["paradigm_alerts_fired"] == 1


class TestStrategyMemoryGetTip:
    """get_tip returns None until 3+ sessions; then surfaces strategic insights."""

    def test_returns_none_when_fewer_than_3_sessions(self, tmp_memory: StrategyMemory) -> None:
        tmp_memory.record_session(domain="healthcare", final_route="ACT")
        tmp_memory.record_session(domain="healthcare", final_route="ACT")
        assert tmp_memory.get_tip("healthcare") is None

    def test_returns_tip_when_decisive_tier_present(self, tmp_memory: StrategyMemory) -> None:
        for _ in range(3):
            tmp_memory.record_session(
                domain="healthcare", final_route="ACT",
                decisive_tier="P2", final_posterior=0.8,
            )
        tip = tmp_memory.get_tip("healthcare")
        assert tip is not None
        assert isinstance(tip, str)
        assert len(tip) > 0

    def test_returns_none_when_no_actionable_signals(self, tmp_memory: StrategyMemory) -> None:
        """All-ACT sessions with no tier hits, no halts, no alerts → no tip to surface."""
        for _ in range(3):
            tmp_memory.record_session(domain="healthcare", final_route="ACT")
        assert tmp_memory.get_tip("healthcare") is None

    def test_returns_none_for_unknown_domain(self, tmp_memory: StrategyMemory) -> None:
        assert tmp_memory.get_tip("nonexistent_domain") is None

    def test_tip_mentions_domain_on_high_halt_rate(self, tmp_memory: StrategyMemory) -> None:
        for _ in range(4):
            tmp_memory.record_session(domain="finance", final_route="HALT", final_posterior=0.2)
        tip = tmp_memory.get_tip("finance")
        assert tip is not None
        assert "finance" in tip.lower() or "HALT" in tip or "halt" in tip.lower()


class TestStrategyMemoryPersistence:
    """Memory survives process restart by writing to disk."""

    def test_data_persists_across_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "eif_memory.json"
        mem1 = StrategyMemory(path=path)
        for _ in range(3):
            mem1.record_session(domain="legal", final_route="ACT")

        mem2 = StrategyMemory(path=path)
        assert mem2._data["legal"]["sessions_seen"] == 3

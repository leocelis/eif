"""Tests for DECLARE phase (C2, C13 - falsification_required, HARKing guard)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from eif.declare.harking_guard import detect_harking
from eif.declare.registry import build_registry
from eif.schemas import AssumptionRegistry, ClaimInput


class TestBuildRegistry:
    """C2: eif_declare returns falsification_required for untested ASSUMED claims."""

    def test_assumed_without_fc_in_falsification_required(self):
        claims = [
            ClaimInput(text="API returns JSON", claim_type="ASSUMED"),
        ]
        registry, stale = build_registry("s1", "deploy", claims)
        assert registry.assumed[0].falsification_condition is None
        # MCP tool reads this from registry; we verify the field is None
        unfalsified = [c for c in registry.assumed if not c.falsification_condition]
        assert len(unfalsified) == 1
        assert unfalsified[0].text == "API returns JSON"

    def test_assumed_with_fc_not_in_required(self):
        claims = [
            ClaimInput(
                text="API returns JSON",
                claim_type="ASSUMED",
                falsification_condition="Response is not JSON",
            ),
        ]
        registry, _ = build_registry("s1", "deploy", claims)
        unfalsified = [c for c in registry.assumed if not c.falsification_condition]
        assert unfalsified == []

    def test_known_claim_segregated_correctly(self):
        claims = [
            ClaimInput(
                text="Python installed",
                claim_type="KNOWN",
                evidence_source="which python3",
            ),
        ]
        registry, _ = build_registry("s1", "deploy", claims)
        assert len(registry.known) == 1
        assert len(registry.assumed) == 0

    def test_empty_decision_raises(self):
        with pytest.raises(ValueError, match="decision string cannot be empty"):
            build_registry("s1", "", [])

    def test_stale_evidence_warning(self):
        old_date = datetime.utcnow() - timedelta(days=45)
        claims = [
            ClaimInput(
                text="Old claim",
                claim_type="ASSUMED",
                retrieved_at=old_date,
            ),
        ]
        _, stale = build_registry("s1", "deploy", claims)
        assert len(stale) == 1
        assert "45" in stale[0] or "Old claim" in stale[0]

    def test_fresh_evidence_no_warning(self):
        claims = [
            ClaimInput(
                text="Fresh claim",
                claim_type="ASSUMED",
                retrieved_at=datetime.utcnow(),
            ),
        ]
        _, stale = build_registry("s1", "deploy", claims)
        assert stale == []


class TestHARKingGuard:
    """C13: harking_flag=True when registry was created after decision timestamp."""

    def test_harking_flag_when_registry_after_decision(self):
        decision_time = datetime.utcnow() - timedelta(minutes=5)
        # Registry created now (after decision_time)
        registry = AssumptionRegistry(
            session_id="s1",
            decision="deploy",
        )
        result = detect_harking(registry, decision_timestamp=decision_time)
        assert result.harking_flag is True

    def test_no_harking_when_registry_before_decision(self):
        future_decision = datetime.utcnow() + timedelta(minutes=5)
        registry = AssumptionRegistry(
            session_id="s1",
            decision="deploy",
        )
        result = detect_harking(registry, decision_timestamp=future_decision)
        assert result.harking_flag is False

    def test_no_decision_timestamp_no_harking(self):
        registry = AssumptionRegistry(session_id="s1", decision="deploy")
        result = detect_harking(registry)
        assert result.harking_flag is False

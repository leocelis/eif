"""Tests for RECORD phase (C8, C9 - ProvenanceRecord UUID, contrary_evidence flag)."""

from __future__ import annotations

import uuid

import pytest

from eif.record.compliance import map_compliance
from eif.record.provenance import assemble_record
from eif.schemas import AssumptionRegistry, ChallengeResult, Claim


def _make_registry(session_id: str = "s1") -> AssumptionRegistry:
    return AssumptionRegistry(
        session_id=session_id,
        decision="Deploy recommendation service",
        known=[
            Claim(
                text="Python installed",
                claim_type="KNOWN",
                evidence_source="which python3",
            )
        ],
    )


class TestProvenanceRecord:
    """C8: ProvenanceRecord has unique UUID4 record_id."""

    def test_record_has_uuid4(self):
        registry = _make_registry()
        record, _, _ = assemble_record(
            session_id="s1",
            decision="Deploy recommendation service",
            registry=registry,
        )
        # Should be a valid UUID4
        parsed = uuid.UUID(record.record_id, version=4)
        assert str(parsed) == record.record_id

    def test_two_records_have_different_ids(self):
        registry = _make_registry()
        r1, _, _ = assemble_record("s1", "decision A", registry)
        r2, _, _ = assemble_record("s1", "decision B", registry)
        assert r1.record_id != r2.record_id

    def test_record_has_session_id(self):
        registry = _make_registry()
        record, _, _ = assemble_record("my-session", "deploy", registry)
        assert record.session_id == "my-session"

    def test_empty_decision_raises(self):
        registry = _make_registry()
        with pytest.raises(ValueError, match="decision string cannot be empty"):
            assemble_record("s1", "", registry)

    def test_stale_evidence_detected(self):
        from datetime import datetime, timedelta
        registry = AssumptionRegistry(
            session_id="s1",
            decision="deploy",
            assumed=[
                Claim(
                    text="API stable",
                    claim_type="ASSUMED",
                    retrieved_at=datetime.utcnow() - timedelta(days=45),
                )
            ],
        )
        _, stale, _ = assemble_record("s1", "deploy", registry)
        assert len(stale) == 1
        assert "API stable" in stale[0]


class TestContraryEvidence:
    """C9: contrary_evidence_considered driven by critic_independence."""

    def test_independent_critic_sets_contrary_true(self):
        registry = _make_registry()
        challenge = ChallengeResult(
            claim_text="API returns JSON",
            critic_independence="DIFFERENT_FAMILY",
            verdict="SURVIVES",
        )
        record, _, _ = assemble_record(
            "s1", "deploy", registry, challenge=challenge
        )
        assert record.contrary_evidence_considered is True

    def test_no_critic_independence_sets_contrary_false(self):
        registry = _make_registry()
        challenge = ChallengeResult(
            claim_text="API returns JSON",
            critic_independence="NONE",
            verdict="SURVIVES",
        )
        record, _, _ = assemble_record(
            "s1", "deploy", registry, challenge=challenge
        )
        assert record.contrary_evidence_considered is False

    def test_no_challenge_sets_contrary_false(self):
        registry = _make_registry()
        record, _, _ = assemble_record("s1", "deploy", registry)
        assert record.contrary_evidence_considered is False

    def test_counter_evidence_also_sets_contrary_true(self):
        registry = _make_registry()
        challenge = ChallengeResult(
            claim_text="API returns JSON",
            critic_independence="NONE",
            counter_evidence=["In some edge cases, returns XML"],
            verdict="NEEDS_REVISION",
        )
        record, _, _ = assemble_record(
            "s1", "deploy", registry, challenge=challenge
        )
        assert record.contrary_evidence_considered is True


class TestCompliance:
    def test_article_12_always_present(self):
        registry = _make_registry()
        record, _, _ = assemble_record("s1", "deploy", registry)
        compliance = map_compliance(record)
        assert "Article 12" in compliance

    def test_article_9_when_high_risk_claim(self):
        registry = AssumptionRegistry(
            session_id="s1",
            decision="deploy",
            assumed=[
                Claim(
                    text="Model is safe",
                    claim_type="ASSUMED",
                    consequence_of_wrong="HIGH",
                )
            ],
        )
        record, _, _ = assemble_record("s1", "deploy", registry)
        compliance = map_compliance(record)
        assert "Article 9" in compliance

    def test_no_article_9_without_high_risk(self):
        registry = _make_registry()
        record, _, _ = assemble_record("s1", "deploy", registry)
        compliance = map_compliance(record)
        assert "Article 9" not in compliance

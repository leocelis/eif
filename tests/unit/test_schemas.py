"""Tests for EIF schemas (C1 - KNOWN claim validation)."""

import pytest
from pydantic import ValidationError

from eif.schemas import (
    CONFORMAL_MIN_HISTORY,
    EIG_THRESHOLD,
    EVIDENCE_STALENESS_DAYS,
    PRIOR_EMPIRICAL_MIN,
    REPLICATE_AGREE_THRESHOLD,
    REPLICATE_FAIL_THRESHOLD,
    THRESHOLD_ACT,
    THRESHOLD_HALT,
    THRESHOLD_REVISE,
    AssumptionRegistry,
    Claim,
)


class TestKnownClaimValidation:
    """C1: KNOWN claim without evidence_source must raise ValidationError."""

    def test_known_claim_requires_source(self):
        with pytest.raises(ValidationError, match="KNOWN claims must have an evidence_source"):
            Claim(
                text="Python is installed",
                claim_type="KNOWN",
                evidence_source=None,
            )

    def test_known_claim_with_source_valid(self):
        c = Claim(
            text="Python is installed",
            claim_type="KNOWN",
            evidence_source="which python3",
        )
        assert c.claim_type == "KNOWN"
        assert c.evidence_source == "which python3"

    def test_assumed_claim_without_source_valid(self):
        c = Claim(text="API returns JSON", claim_type="ASSUMED")
        assert c.claim_type == "ASSUMED"
        assert c.evidence_source is None

    def test_guessed_claim_without_source_valid(self):
        c = Claim(text="Latency < 100ms", claim_type="GUESSED")
        assert c.claim_type == "GUESSED"


class TestConstants:
    """Verify all constants match the tech spec design decisions."""

    def test_threshold_act(self):
        assert THRESHOLD_ACT == 0.70

    def test_threshold_revise(self):
        assert THRESHOLD_REVISE == 0.40

    def test_threshold_halt(self):
        assert THRESHOLD_HALT == 0.20

    def test_eig_threshold(self):
        assert EIG_THRESHOLD == 0.01

    def test_evidence_staleness_days(self):
        assert EVIDENCE_STALENESS_DAYS == 30

    def test_prior_empirical_min(self):
        assert PRIOR_EMPIRICAL_MIN == 10

    def test_replicate_agree_threshold(self):
        assert REPLICATE_AGREE_THRESHOLD == 0.80

    def test_replicate_fail_threshold(self):
        assert REPLICATE_FAIL_THRESHOLD == 0.50

    def test_conformal_min_history(self):
        assert CONFORMAL_MIN_HISTORY == 20


class TestAssumptionRegistry:
    """High-risk claims surface correctly in the assumption check card."""

    def test_high_risk_assumed_returns_at_most_three(self):
        claims = [
            Claim(text=f"claim {i}", claim_type="ASSUMED", consequence_of_wrong="HIGH")
            for i in range(5)
        ]
        registry = AssumptionRegistry(
            session_id="s1",
            decision="deploy",
            assumed=claims,
        )
        assert len(registry.high_risk_assumed) <= 3

    def test_high_risk_assumed_excludes_medium_risk(self):
        registry = AssumptionRegistry(
            session_id="s1",
            decision="deploy",
            assumed=[
                Claim(text="low claim", claim_type="ASSUMED", consequence_of_wrong="LOW"),
            ],
        )
        assert registry.high_risk_assumed == []

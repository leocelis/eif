"""Shared pytest fixtures for the EIF test suite."""

from __future__ import annotations

import pytest

from eif.schemas import (
    AssumptionRegistry,
    CalibrationResult,
    ChallengeResult,
    Claim,
    ExplanationArtifact,
    ExplanationDetail,
    FalsificationCondition,
)

# ── Claim fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def known_claim() -> Claim:
    return Claim(
        text="Python 3.11 is installed",
        claim_type="KNOWN",
        evidence_source="which python3 → /usr/bin/python3",
    )


@pytest.fixture
def assumed_claim() -> Claim:
    return Claim(
        text="The API returns JSON",
        claim_type="ASSUMED",
        consequence_of_wrong="HIGH",
    )


@pytest.fixture
def guessed_claim() -> Claim:
    return Claim(
        text="Latency is under 100ms",
        claim_type="GUESSED",
    )


# ── Registry fixture ──────────────────────────────────────────────────────────

@pytest.fixture
def simple_registry(known_claim, assumed_claim) -> AssumptionRegistry:
    return AssumptionRegistry(
        session_id="test-session",
        decision="Deploy the recommendation service",
        known=[known_claim],
        assumed=[assumed_claim],
    )


# ── FalsificationCondition fixture ───────────────────────────────────────────

@pytest.fixture
def falsification_condition() -> FalsificationCondition:
    return FalsificationCondition(
        claim_text="The API returns JSON",
        condition="Response Content-Type is not application/json",
        threshold="Any single failure falsifies the claim",
        test_procedure="Send GET /health; inspect Content-Type header",
    )


# ── CalibrationResult fixture ─────────────────────────────────────────────────

@pytest.fixture
def calibration_result() -> CalibrationResult:
    return CalibrationResult(
        claim_text="The API returns JSON",
        prior=0.5,
        likelihood=0.8,
        posterior=0.727,
        confidence_tier="HIGH",
        prior_strategy="max_entropy",
    )


# ── ChallengeResult fixture ───────────────────────────────────────────────────

@pytest.fixture
def independent_challenge() -> ChallengeResult:
    return ChallengeResult(
        claim_text="The API returns JSON",
        critic_model="gpt-4o",
        critic_independence="DIFFERENT_FAMILY",
        counter_evidence_found=True,
        counter_evidence=["In test env, /timeout returns text/plain"],
        verdict="NEEDS_REVISION",
    )


@pytest.fixture
def self_challenge() -> ChallengeResult:
    return ChallengeResult(
        claim_text="The API returns JSON",
        critic_independence="NONE",
        verdict="SURVIVES",
    )


# ── ExplanationArtifact fixture ───────────────────────────────────────────────

@pytest.fixture
def good_explanation() -> ExplanationArtifact:
    return ExplanationArtifact(
        prior_explanation="JSON is returned because Flask defaults to it",
        new_explanation="JSON is returned because the route uses jsonify(), which "
                        "sets Content-Type: application/json; this is the only code path",
        details=[
            ExplanationDetail(
                detail_text="route uses jsonify()",
                prediction_impact="If jsonify() is removed, Content-Type becomes text/html",
            ),
        ],
        hard_to_vary_verdict="PASS",
        testable_predictions=["Remove jsonify() → Content-Type changes to text/html"],
    )

"""Integration test: full EIF loop DECLARE → FALSIFY → CALIBRATE → UPDATE → EXPLAIN → RECORD.

Scenario: An agent must decide whether to deploy a recommendation service.
It has two claims - one KNOWN, one ASSUMED. We walk the full EIF loop and
verify the ProvenanceRecord is coherent at the end.
"""

from __future__ import annotations

import uuid

from eif.calibrate.bayesian import compute_posterior
from eif.calibrate.prior_strategy import select_prior_strategy
from eif.causal_gate.intervention import check_intervention, classify_causal_level
from eif.declare.registry import build_registry
from eif.explain.artifact import build_artifact
from eif.falsify.condition import build_condition
from eif.falsify.sprt import run_sprt
from eif.programme.monitor import compute_status
from eif.record.compliance import map_compliance
from eif.record.provenance import assemble_record
from eif.schemas import (
    THRESHOLD_ACT,
    THRESHOLD_HALT,
    THRESHOLD_REVISE,
    ChallengeResult,
    ClaimInput,
    ProgrammeSignals,
)
from eif.update.eig import compute_eig
from eif.update.posterior import sequential_update
from eif.update.stopping import evaluate_stopping

DECISION = "Deploy recommendation service v2 to production"
SESSION_ID = str(uuid.uuid4())


class TestFullEIFLoop:
    """Walk the complete EIF loop and verify invariants at each phase."""

    # ── Phase 1: DECLARE ─────────────────────────────────────────────────────

    def test_phase1_declare(self):
        claims = [
            ClaimInput(
                text="Redis is available on port 6379",
                claim_type="KNOWN",
                evidence_source="redis-cli ping → PONG",
                consequence_of_wrong="HIGH",
            ),
            ClaimInput(
                text="Users prefer collaborative filtering over content-based",
                claim_type="ASSUMED",
                consequence_of_wrong="MEDIUM",
            ),
        ]
        registry, stale = build_registry(SESSION_ID, DECISION, claims)

        assert len(registry.known) == 1
        assert len(registry.assumed) == 1
        assert stale == []
        assert registry.decision == DECISION

        # C2: assumed claim without FC must appear in unfalsified list
        unfalsified = [c for c in registry.assumed if not c.falsification_condition]
        assert len(unfalsified) == 1

    # ── Phase 2: FALSIFY ─────────────────────────────────────────────────────

    def test_phase2_falsify(self):
        fc = build_condition(
            claim_text="Users prefer collaborative filtering",
            condition="CTR of collaborative < CTR of content-based",
            threshold="CTR delta > 5% for >= 1000 users",
            test_procedure="A/B test for 2 weeks",
            alpha=0.05,
            beta=0.10,
            effect_size=0.2,
        )

        # Simulate 15 positive observations (A/B test shows CF wins)
        observations = [True] * 15
        result = run_sprt(fc, observations)

        assert result.decision in ("ACCEPT", "CONTINUE")  # positive observations support H₀
        assert result.likelihood_ratio > 0
        assert result.observations_count == 15

    # ── Phase 2.5: CAUSAL GATE ───────────────────────────────────────────────

    def test_phase2_5_causal_gate(self):
        hypothesis = "Users prefer collaborative filtering and content-based features cause CTR lift"
        level = classify_causal_level(hypothesis)
        intervention_required, disjunctive = check_intervention(
            hypothesis=hypothesis,
            causal_level=level,
            evidence_level="ASSOCIATION",
        )
        # "and" present + association evidence → disjunctive bias flag
        assert disjunctive is True

    # ── Phase 3: CALIBRATE ───────────────────────────────────────────────────

    def test_phase3_calibrate(self):
        strategy, _ = select_prior_strategy(
            prior_provided=False,
            calibration_history_size=5,
        )
        assert strategy == "max_entropy"

        posterior, likelihood = compute_posterior(
            prior=0.5,
            evidence_supports=True,
            likelihood_estimate=0.75,
        )
        assert 0.5 < posterior < 1.0
        assert likelihood == 0.75

    # ── Phase 5: UPDATE ──────────────────────────────────────────────────────

    def test_phase5_update_and_stopping(self):
        prior = 0.5
        posterior, _ = sequential_update(prior_posterior=prior, evidence_supports=True)
        eig = compute_eig(prior=prior, posterior=posterior)

        triggered, reason = evaluate_stopping(eig=eig)
        # With a meaningful update, EIG should exceed threshold
        assert eig > 0.0
        # Stopping should NOT trigger on a meaningful first update
        if eig >= 0.01:
            assert triggered is False

    # ── Phase 5.5: EXPLAIN ───────────────────────────────────────────────────

    def test_phase5_5_explain(self):
        artifact, _ = build_artifact(
            prior_explanation="We assumed users prefer CF",
            new_explanation=(
                "A/B test with 3,500 users shows CF achieves 12% higher CTR than "
                "content-based; the mechanism is that CF incorporates social signals "
                "which are not available in content features"
            ),
            details=[
                {
                    "detail_text": "social signals not in content features",
                    "prediction_impact": (
                        "Remove social signal access → CF advantage drops to near 0%"
                    ),
                },
            ],
            testable_predictions=[
                "Restrict user history access → CF CTR drops below content-based",
            ],
        )
        assert artifact.hard_to_vary_verdict == "PASS"
        assert len(artifact.testable_predictions) == 1

    # ── Phase 6: RECORD ──────────────────────────────────────────────────────

    def test_phase6_record(self):
        registry, _ = build_registry(
            SESSION_ID,
            DECISION,
            [
                ClaimInput(
                    text="Redis available",
                    claim_type="KNOWN",
                    evidence_source="redis-cli ping",
                )
            ],
        )
        challenge = ChallengeResult(
            claim_text="Users prefer CF",
            critic_independence="DIFFERENT_OBJECTIVE",
            counter_evidence=["Content-based outperforms in cold-start scenarios"],
            verdict="NEEDS_REVISION",
        )
        record, stale, harked = assemble_record(
            session_id=SESSION_ID,
            decision=DECISION,
            registry=registry,
            challenge=challenge,
        )

        # C8: UUID4 present
        uuid.UUID(record.record_id, version=4)

        # C9: contrary_evidence_considered = True (DIFFERENT_OBJECTIVE critic)
        assert record.contrary_evidence_considered is True

        # Article 12 compliance always present
        compliance = map_compliance(record)
        assert "Article 12" in compliance

    # ── Phase 8: PROGRAMME HEALTH ────────────────────────────────────────────

    def test_phase8_programme_health(self):
        signals = ProgrammeSignals(
            novel_prediction_rate=0.4,
            confirmed_prediction_rate=0.35,
            patch_rate=0.1,
            oscillation_count=0,
        )
        status = compute_status(signals)
        assert status == "PROGRESSIVE"

    # ── Decision thresholds respected ────────────────────────────────────────

    def test_decision_thresholds_ordered(self):
        assert THRESHOLD_ACT > THRESHOLD_REVISE > THRESHOLD_HALT > 0

    def test_posterior_routing(self):
        high_posterior = 0.85
        mid_posterior = 0.55
        low_posterior = 0.25

        assert high_posterior >= THRESHOLD_ACT     # → MAINTAIN_COURSE
        assert THRESHOLD_REVISE <= mid_posterior < THRESHOLD_ACT  # → gather more evidence
        assert THRESHOLD_HALT <= low_posterior < THRESHOLD_REVISE  # → RETURN_TO_DECLARE

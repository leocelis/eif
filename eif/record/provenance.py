"""Assemble ProvenanceRecord from session state."""

from __future__ import annotations

import logging
from datetime import datetime

from eif.declare.harking_guard import detect_harking
from eif.record.compliance import map_compliance
from eif.schemas import (
    ENGINE_VERSION,
    EVIDENCE_STALENESS_DAYS,
    AssumptionRegistry,
    CalibrationResult,
    CausalEvidenceResult,
    CausalGateResult,
    ChallengeResult,
    ExplanationArtifact,
    FalsificationCondition,
    OversightStatus,
    ProvenanceRecord,
    SPRTResult,
    UpdateResult,
)

_log = logging.getLogger(__name__)


def assemble_record(
    session_id: str,
    decision: str,
    registry: AssumptionRegistry,
    falsification_conditions: list[FalsificationCondition] | None = None,
    sprt_results: list[SPRTResult] | None = None,
    causal_gate: CausalGateResult | None = None,
    causal_evidence_result: CausalEvidenceResult | None = None,
    calibration: list[CalibrationResult] | None = None,
    challenge: ChallengeResult | None = None,
    updates: list[UpdateResult] | None = None,
    explanation: ExplanationArtifact | None = None,
    models_used: list[str] | None = None,
    tools_invoked: list[str] | None = None,
    human_oversight: OversightStatus = "NOT_NEEDED",
    metric_quality_flags: list[str] | None = None,  # F17: from eif_verify evidence collection
    input_guard: dict | None = None,  # IG6: InputGuardResult snapshot for audit trail
) -> tuple[ProvenanceRecord, list[str], list[str]]:
    """Assemble a ProvenanceRecord from session components.

    Returns:
        (record, stale_evidence_warnings, harked_conditions)
    """
    if not decision:
        raise ValueError("decision string cannot be empty")

    now = datetime.utcnow()

    # Compute contrary_evidence_considered (ENGINE C9):
    # True when EITHER condition holds:
    #   (a) an independent critic was used (critic_independence != NONE) - the critic
    #       process itself constitutes considering contrary evidence even when no
    #       counter-evidence strings are returned (the critic may find none and that
    #       is still a valid challenge outcome); OR
    #   (b) explicit counter-evidence strings were supplied - even through a non-independent
    #       path, providing counter_evidence means opposing evidence was actively gathered.
    # Both pathways satisfy the C9 intent: the agent did not just self-validate.
    # (eif_engine_intent.yaml ENGINE C9; CONSENSAGENT ACL 2025 §3)
    contrary_evidence_considered = (
        challenge is not None
        and (
            challenge.critic_independence != "NONE"
            or len(challenge.counter_evidence) > 0
        )
    )

    # Check stale evidence
    stale_warnings: list[str] = []
    all_claims = registry.known + registry.assumed + registry.guessed
    for claim in all_claims:
        if claim.retrieved_at is not None:
            age_days = (now - claim.retrieved_at).days
            if age_days > EVIDENCE_STALENESS_DAYS:
                warning = (
                    f"Claim {claim.text!r} evidence retrieved {age_days} days ago "
                    f"(> {EVIDENCE_STALENESS_DAYS})"
                )
                stale_warnings.append(warning)
                _log.warning("STALE_EVIDENCE: %s", warning)

    # Detect HARKed conditions (C13 - ENGINE C13):
    # Delegates to detect_harking (Trigger 3 / V3) so the registered_at > verified_at
    # check lives in a single place (harking_guard.py) rather than being duplicated here.
    # detect_harking returns a registry copy with harking_flag and harking_reasons set.
    registry = detect_harking(
        registry,
        decision_timestamp=None,          # V1 timestamp not applicable in assemble_record
        falsification_conditions=list(falsification_conditions or []),
    )
    # Build harked_conditions list from the updated registry reasons for the return value.
    harked_conditions: list[str] = getattr(registry, "harking_reasons", [])

    # CG6: set causal_unverified flag when NO_EVIDENCE on a HIGH-consequence claim
    causal_unverified = (
        causal_evidence_result is not None
        and causal_evidence_result.provenance_flag == "CAUSAL_UNVERIFIED"
    )
    if causal_unverified:
        _log.warning(
            "CAUSAL_UNVERIFIED: HIGH causal claim could not be independently verified "
            "(EU AI Act Art. 9): %r",
            causal_evidence_result.claim_text if causal_evidence_result else "",
        )

    # Research Object fingerprint (arXiv:2604.11261)
    fingerprint = ProvenanceRecord.compute_fingerprint(decision, registry)
    config_snapshot: dict[str, str] = {"eif_engine": ENGINE_VERSION}
    if models_used:
        for i, m in enumerate(models_used):
            config_snapshot[f"model_{i}"] = m

    record = ProvenanceRecord(
        session_id=session_id,
        decision=decision,
        timestamp=now,
        registry=registry,
        falsification_conditions=falsification_conditions or [],
        sprt_results=sprt_results or [],
        causal_gate=causal_gate,
        causal_evidence_result=causal_evidence_result,
        causal_unverified=causal_unverified,
        calibration=calibration or [],
        challenge=challenge,
        updates=updates or [],
        explanation=explanation,
        models_used=models_used or [],
        tools_invoked=tools_invoked or [],
        human_oversight=human_oversight,
        contrary_evidence_considered=contrary_evidence_considered,
        input_fingerprint=fingerprint,
        model_config_snapshot=config_snapshot,
        metric_quality_flags=metric_quality_flags or [],  # F17
        input_guard=input_guard,  # IG6: persists InputGuardResult for full audit trail
    )

    # Populate articles_covered so EU AI Act mapping is persisted with the record
    # rather than recomputed on every read by eif_compliance_report.
    record.articles_covered = map_compliance(record)

    return record, stale_warnings, harked_conditions

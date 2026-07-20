"""Build ExplanationArtifact objects.

Domain specificity logic lives in eif.explain.hard_to_vary (check_domain_specificity,
extract_anchor_tokens). There is no separate explain/domain.py module - hard_to_vary.py
is the canonical home for both hard-to-vary checks and domain specificity (EE1).
"""

from __future__ import annotations

from eif.explain.hard_to_vary import check_domain_specificity, check_hard_to_vary
from eif.explain.reach import classify_reach
from eif.schemas import ExplanationArtifact, ExplanationDetail, HardToVaryVerdict, ReachScope


def build_artifact(
    prior_explanation: str,
    new_explanation: str,
    details: list[dict],
    testable_predictions: list[str],
    disconfirming_evidence: str | None = None,
    reach: ReachScope | None = None,
    reach_implications: str | None = None,
    corroborated: bool = False,
    system_context: str | None = None,
) -> tuple[ExplanationArtifact, list[str]]:
    """Build and validate an ExplanationArtifact.

    Args:
        system_context: Optional domain-context string (v4.1 domain-specificity gate, S14).
            When provided and >= 3 anchor tokens are extractable, each detail is checked
            against high-specificity tokens from the context. Details with no anchor hit
            fail as domain-agnostic (easy to vary by swapping domain).

    Returns (artifact, failed_details) where failed_details is a list of
    detail_text strings that failed either the hard-to-vary or domain-specificity check.
    """
    if not new_explanation:
        raise ValueError("new_explanation cannot be empty")
    if not testable_predictions:
        raise ValueError("At least one testable_prediction is required")

    detail_objects = [
        ExplanationDetail(
            detail_text=d["detail_text"],
            prediction_impact=d.get("prediction_impact", ""),
        )
        for d in details
    ]

    # Primary hard-to-vary check (Deutsch criterion)
    verdict: HardToVaryVerdict = check_hard_to_vary(detail_objects)

    # v4.1: domain-specificity gate (S14 / eif_explain_coldstart_intent).
    # Only fires when system_context is non-empty and >= 3 anchor tokens are extractable;
    # otherwise returns PASS immediately (deterministic, no LLM call).
    if verdict == "PASS" and system_context:
        verdict = check_domain_specificity(detail_objects, system_context)

    failed_details = [
        d.detail_text for d in detail_objects
        if not d.prediction_impact.strip()
    ]

    inferred_reach = reach or classify_reach(new_explanation)

    artifact = ExplanationArtifact(
        prior_explanation=prior_explanation,
        disconfirming_evidence=disconfirming_evidence,
        new_explanation=new_explanation,
        details=detail_objects,
        hard_to_vary_verdict=verdict,
        testable_predictions=testable_predictions,
        reach=inferred_reach,
        reach_implications=reach_implications,
        corroborated=corroborated,
    )

    return artifact, failed_details

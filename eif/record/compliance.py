"""Map ProvenanceRecord to EU AI Act compliance articles."""

from __future__ import annotations

from eif.schemas import ProvenanceRecord


def map_compliance(record: ProvenanceRecord) -> dict[str, list[str]]:
    """Map a ProvenanceRecord to relevant EU AI Act articles.

    Article 9  - Risk management: applies when HIGH-risk claims exist
    Article 12 - Logging: always applies (we're producing a record)
    Article 13 - Transparency: applies when an explanation is present
    Article 14 - Human oversight: applies when ESCALATED
    """
    articles: dict[str, list[str]] = {}

    all_claims = (
        record.registry.known
        + record.registry.assumed
        + record.registry.guessed
    )
    high_risk_present = any(c.consequence_of_wrong == "HIGH" for c in all_claims)

    # CG6: Article 9 also fires when a HIGH-consequence causal claim could not
    # be independently verified (CausalEvidenceProbe returned NO_EVIDENCE), even
    # when no claim is explicitly marked HIGH consequence in the registry.
    causal_unverified = getattr(record, "causal_unverified", False)

    if high_risk_present or causal_unverified:
        reasons = ["Risk management system required for high-risk AI systems."]
        if high_risk_present:
            reasons.append(
                f"High-risk claims detected: {[c.text for c in all_claims if c.consequence_of_wrong == 'HIGH']}"
            )
        if causal_unverified:
            reasons.append(
                "Causal claim could not be independently verified - manual review required."
            )
        articles["Article 9"] = reasons

    articles["Article 12"] = [
        "Logging obligation: this ProvenanceRecord satisfies Article 12 logging requirements.",
        f"Record ID: {record.record_id}",
        f"Session: {record.session_id}",
        f"Timestamp: {record.timestamp.isoformat()}",
    ]

    if record.explanation is not None:
        articles["Article 13"] = [
            "Transparency obligation: explanation artifact present.",
            f"Explanation reach: {record.explanation.reach}",
            f"Hard-to-vary verdict: {record.explanation.hard_to_vary_verdict}",
        ]

    if record.human_oversight == "ESCALATED":
        articles["Article 14"] = [
            "Human oversight obligation triggered: record marked ESCALATED.",
            "Human review required before proceeding.",
        ]

    return articles

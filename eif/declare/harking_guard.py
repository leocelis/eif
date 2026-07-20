"""Detect HARKing (Hypothesizing After Results are Known).

V1: A claim is HARKed when it was added after the decision timestamp - meaning
the agent committed a claim post-hoc rather than pre-registering it.

V2 (F9C2 - Lakens 2021): CONFIRMATORY claims must have a falsification_condition
registered BEFORE evidence is collected. A CONFIRMATORY claim without a
falsification_condition is flagged as a HARKING risk regardless of timestamps,
because the claim cannot be confirmed to be pre-registered without a
verifiable falsification test.

V3 (ENGINE C13): a FalsificationCondition whose registered_at timestamp is
LATER than the Claim.verified_at timestamp is definitionally post-hoc - 
the falsification test was registered AFTER the claim was already verified.

Research:
  Lakens (2021) - Perspectives on Psychological Science 16(3), 639-648:
  "Inferential claims from exploratory analysis contaminate confirmatory inference;
  explicit labeling required. CONFIRMATORY claims require pre-registered
  falsification conditions to maintain inferential validity."
"""

from __future__ import annotations

import logging
from datetime import datetime

from eif.schemas import AssumptionRegistry, FalsificationCondition

_log = logging.getLogger(__name__)


def detect_harking(
    registry: AssumptionRegistry,
    decision_timestamp: datetime | None = None,
    falsification_conditions: list[FalsificationCondition] | None = None,
) -> AssumptionRegistry:
    """Flag registry.harking_flag if any claim is a HARKING risk.

    Three triggers (any suffices):

    1. Timestamp trigger (V1): registry.created_at > decision_timestamp.
       Requires decision_timestamp to be provided.

    2. Confirmatory-without-condition trigger (V2 F9C2): any CONFIRMATORY
       claim that lacks a falsification_condition is a HARKING risk.
       Rationale: without a pre-registered falsification test, there is no
       verifiable evidence the hypothesis was stated before results were known.
       (Lakens 2021; EIF v2 intent F9C2)

    3. Post-hoc condition trigger (V3 ENGINE C13): a FalsificationCondition
       whose registered_at is AFTER the matched Claim.verified_at.
       The condition was registered after the claim was already verified - 
       definitionally post-hoc (hypothesizing after results known).
       Requires falsification_conditions to be provided.

    Returns a registry copy with harking_flag set and harking_reasons populated.
    """
    harking = False
    harking_reasons: list[str] = []

    # Trigger 1: timestamp (V1)
    if decision_timestamp is not None and registry.created_at > decision_timestamp:
        harking = True
        harking_reasons.append(
            f"Registry created at {registry.created_at.isoformat()} after decision "
            f"timestamp {decision_timestamp.isoformat()} - claims may be post-hoc."
        )
        _log.warning(
            "HARKING_DETECTED: registry created at %s after decision timestamp %s",
            registry.created_at.isoformat(),
            decision_timestamp.isoformat(),
        )

    # Trigger 2: CONFIRMATORY claim without falsification_condition (V2 F9C2)
    all_claims = list(registry.known) + list(registry.assumed) + list(registry.guessed)
    for claim in all_claims:
        if claim.claim_mode == "CONFIRMATORY" and not claim.falsification_condition:
            harking = True
            harking_reasons.append(
                f"CONFIRMATORY claim without falsification_condition: {claim.text[:80]!r}. "
                "Pre-registration requires a falsification condition to be stated before "
                "evidence is collected (Lakens 2021, F9C2)."
            )
            _log.warning(
                "HARKING_RISK (F9C2): CONFIRMATORY claim missing falsification_condition: %s",
                claim.text[:80],
            )

    # Trigger 3: FalsificationCondition registered AFTER claim.verified_at (V3 ENGINE C13)
    if falsification_conditions:
        claims_by_text = {c.text: c for c in all_claims}
        for fc in falsification_conditions:
            matched = claims_by_text.get(fc.claim_text)
            if matched is not None and matched.verified_at is not None:
                if fc.registered_at > matched.verified_at:
                    harking = True
                    harking_reasons.append(
                        f"FalsificationCondition registered at {fc.registered_at.isoformat()} "
                        f"AFTER claim already verified at {matched.verified_at.isoformat()} - "
                        f"post-hoc condition (ENGINE C13): {fc.condition!r}"
                    )
                    _log.warning(
                        "HARKING_RISK (C13): FC registered_at %s > claim.verified_at %s for %r",
                        fc.registered_at.isoformat(),
                        matched.verified_at.isoformat(),
                        fc.claim_text[:60],
                    )

    return registry.model_copy(update={"harking_flag": harking, "harking_reasons": harking_reasons})

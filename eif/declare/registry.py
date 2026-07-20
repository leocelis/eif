"""Build an AssumptionRegistry from a list of ClaimInput objects."""

from __future__ import annotations

import logging
from datetime import datetime

from eif.schemas import (
    EVIDENCE_STALENESS_DAYS,
    AssumptionRegistry,
    Claim,
    ClaimInput,
    ClaimMode,
)

_log = logging.getLogger(__name__)


def build_registry(
    session_id: str,
    decision: str,
    claims: list[ClaimInput],
    decision_timestamp: datetime | None = None,
    prior_overrides: dict[str, float] | None = None,
) -> tuple[AssumptionRegistry, list[str]]:
    """Convert ClaimInput list into an AssumptionRegistry.

    Args:
        prior_overrides: optional dict from InputGuardResult.prior_overrides.
            Maps claim_text -> degraded float prior. Claims whose text matches
            a key in prior_overrides are reclassified:
              prior >= 0.70  → KNOWN
              prior >= 0.35  → ASSUMED
              prior <  0.35  → GUESSED
            The sentinel key "__override_turn__" forces all claims to GUESSED.

    Returns:
        (registry, stale_warnings) where stale_warnings is a list of claim
        texts whose retrieved_at is older than EVIDENCE_STALENESS_DAYS.

    Exploratory/confirmatory (Lakens 2021; F9 from EIF v2 intent):
        EXPLORATORY claims generate hypotheses; CONFIRMATORY claims test them.
        When a session contains ONLY EXPLORATORY claims, HALT verdicts are
        advisory - confirmatory replication is required before acting.
        build_registry() itself does not produce HALT verdicts, but it sets
        exploration_flag so the downstream caller (eif_declare, eif_verify) can
        surface the warning. Returned via stale_warnings as a distinguished
        "EXPLORATION_ONLY:" prefix to avoid a schema change at this layer.
    """
    if not decision:
        raise ValueError("decision string cannot be empty")

    prior_overrides = prior_overrides or {}
    _force_guessed = "__override_turn__" in prior_overrides

    def _override_type(text: str, original_type: str) -> str:
        if _force_guessed:
            return "GUESSED"
        if text in prior_overrides:
            p = prior_overrides[text]
            if p >= 0.70:
                return "KNOWN"
            if p >= 0.35:
                return "ASSUMED"
            return "GUESSED"
        return original_type

    known: list[Claim] = []
    assumed: list[Claim] = []
    guessed: list[Claim] = []
    stale_warnings: list[str] = []

    now = datetime.utcnow()

    for ci in claims:
        claim = Claim(
            text=ci.text,
            claim_type=ci.claim_type,
            basis=ci.basis,
            evidence_source=ci.evidence_source,
            falsification_condition=ci.falsification_condition,
            consequence_of_wrong=ci.consequence_of_wrong,
            retrieved_at=ci.retrieved_at,
            claim_mode=ci.claim_mode,
        )

        if claim.claim_type == "KNOWN" and not claim.evidence_source:
            raise ValueError(f"KNOWN claims must have an evidence_source: {claim.text!r}")

        if claim.retrieved_at is not None:
            age_days = (now - claim.retrieved_at).days
            if age_days > EVIDENCE_STALENESS_DAYS:
                stale_warnings.append(
                    f"Claim {claim.text!r} evidence retrieved {age_days} days ago "
                    f"(> {EVIDENCE_STALENESS_DAYS})"
                )
                _log.warning("STALE_EVIDENCE: %s", stale_warnings[-1])

        effective_type = _override_type(claim.text, claim.claim_type)
        if effective_type == "KNOWN":
            known.append(claim)
        elif effective_type == "ASSUMED":
            assumed.append(claim)
        else:
            guessed.append(claim)

    registry = AssumptionRegistry(
        session_id=session_id,
        decision=decision,
        known=known,
        assumed=assumed,
        guessed=guessed,
    )

    # Exploratory-only detection (Lakens 2021 / EIF v2 F9).
    all_claims = known + assumed + guessed
    modes: set[ClaimMode] = {c.claim_mode for c in all_claims}
    if modes and modes == {"EXPLORATORY"}:
        stale_warnings.append(
            "EXPLORATION_ONLY: All claims are EXPLORATORY. HALT verdicts are advisory - "
            "confirmatory replication is required before acting on these findings."
        )

    # F9C2: HARKing risk - any CONFIRMATORY claim without a falsification_condition
    # is a Hypothesizing After Results Known risk (Lakens 2021). Flag it regardless
    # of timestamp so the pipeline can surface the warning.
    harking_flag = any(
        c.claim_mode == "CONFIRMATORY" and not c.falsification_condition
        for c in all_claims
    )
    if harking_flag:
        registry = AssumptionRegistry(
            session_id=registry.session_id,
            decision=registry.decision,
            known=registry.known,
            assumed=registry.assumed,
            guessed=registry.guessed,
            harking_flag=True,
        )
        _log.warning(
            "HARKING_RISK: session=%s has CONFIRMATORY claim(s) without a "
            "pre-registered falsification_condition (F9C2).",
            session_id,
        )

    return registry, stale_warnings

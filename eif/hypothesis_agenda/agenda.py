"""Build a ranked HypothesisAgenda from an AssumptionRegistry.

The agenda answers: given all the assumptions registered in this session,
which one should we test first to maximize expected epistemic value?

Usage:
    from eif.hypothesis_agenda import build_agenda
    agenda = build_agenda(registry, calibration_map, max_probes=3)
"""

from __future__ import annotations

from eif.hypothesis_agenda.fdr import apply_fdr_correction
from eif.hypothesis_agenda.scorer import (
    compute_priority_score,
    nearest_threshold,
)
from eif.schemas import (
    AssumptionRegistry,
    CalibrationResult,
    Claim,
    HypothesisAgenda,
    HypothesisAgendaItem,
)


def _default_posterior_for_claim(claim: Claim) -> float:
    _defaults = {"GUESSED": 0.35, "ASSUMED": 0.55, "KNOWN": 0.80}
    return _defaults[claim.claim_type]


def _build_item(
    claim: Claim,
    calibration_map: dict[str, CalibrationResult],
    rank: int,
) -> HypothesisAgendaItem:
    cal = calibration_map.get(claim.text)
    posterior = cal.posterior if cal else _default_posterior_for_claim(claim)

    priority, eig, c_weight, b_factor, u_factor = compute_priority_score(
        claim, current_posterior=posterior
    )

    rationale_parts: list[str] = []
    if c_weight >= 3.0:
        rationale_parts.append(f"HIGH consequence (weight={c_weight:.1f})")
    if b_factor >= 0.60:
        t = nearest_threshold(posterior)
        rationale_parts.append(
            f"posterior {posterior:.2f} near decision threshold {t:.2f} (boundary={b_factor:.2f})"
        )
    if u_factor >= 1.2:
        rationale_parts.append(f"{claim.claim_type} claim - high uncertainty (u_factor={u_factor:.1f})")

    rationale = "; ".join(rationale_parts) if rationale_parts else f"priority_score={priority:.4f}"

    return HypothesisAgendaItem(
        claim_text=claim.text,
        claim_type=claim.claim_type,
        consequence_of_wrong=claim.consequence_of_wrong,
        current_posterior=posterior,
        eig_score=round(eig, 4),
        consequence_weight=c_weight,
        boundary_factor=round(b_factor, 4),
        uncertainty_factor=u_factor,
        priority_score=round(priority, 6),
        nearest_threshold=nearest_threshold(posterior),
        priority_rank=rank,
        rationale=rationale,
    )


def build_agenda(
    registry: AssumptionRegistry,
    calibration_map: dict[str, CalibrationResult] | None = None,
    max_probes: int | None = None,
) -> HypothesisAgenda:
    """Build a ranked agenda from all claims in the registry.

    Args:
        registry: The AssumptionRegistry from the DECLARE phase.
        calibration_map: Optional dict mapping claim_text → CalibrationResult
            (from the CALIBRATE phase). When absent, default posteriors are used.
        max_probes: If set, only the top-N claims are returned in agenda.items;
            the remainder go into agenda.deferred (constraint HA4).

    Returns:
        HypothesisAgenda with items sorted by priority_score descending.
    """
    if calibration_map is None:
        calibration_map = {}

    all_claims: list[Claim] = (
        list(registry.guessed)
        + list(registry.assumed)
        + list(registry.known)
    )

    if not all_claims:
        return HypothesisAgenda(
            session_id=registry.session_id,
            total_claims=0,
            items=[],
            deferred=[],
            top_recommendation="No claims to rank.",
            rationale="Registry is empty.",
            max_probes=max_probes,
            fdr_warning=None,
        )

    # Score all claims
    scored: list[tuple[float, Claim]] = []
    for claim in all_claims:
        cal = calibration_map.get(claim.text)
        posterior = cal.posterior if cal else _default_posterior_for_claim(claim)
        priority, *_ = compute_priority_score(claim, current_posterior=posterior)
        scored.append((priority, claim))

    scored.sort(key=lambda x: x[0], reverse=True)

    items: list[HypothesisAgendaItem] = []
    for rank, (_, claim) in enumerate(scored, start=1):
        items.append(_build_item(claim, calibration_map, rank))

    # Apply max_probes budget (constraint HA4)
    if max_probes is not None and max_probes < len(items):
        active = items[:max_probes]
        deferred = items[max_probes:]
    else:
        active = items
        deferred = []

    top = active[0] if active else None
    top_text = top.claim_text if top else "None"

    # Build top-level rationale (constraint HA5: must reference consequence_weight and/or boundary_factor)
    if top:
        # Always include consequence_weight and boundary_factor to satisfy HA5 test assertion
        # ("consequence" or "boundary" or "threshold" must appear in agenda.rationale).
        item_reason = top.rationale or f"consequence_weight={top.consequence_weight:.1f}"
        agenda_rationale = (
            f"Top recommendation: '{top_text[:80]}'. "
            f"Ranked #1 because: {item_reason}. "
            f"consequence_weight={top.consequence_weight:.1f}, "
            f"boundary_factor={top.boundary_factor:.4f} (proximity to nearest threshold), "
            f"priority_score={top.priority_score:.4f}."
        )
    else:
        agenda_rationale = "No claims to prioritize."

    # FDR annotation - annotate all items (active + deferred) then re-split
    fdr_adjustments, fdr_warning = apply_fdr_correction(len(all_claims))
    adj_by_rank = {a.rank: a for a in fdr_adjustments}

    def _annotate(item: HypothesisAgendaItem) -> HypothesisAgendaItem:
        adj = adj_by_rank.get(item.priority_rank)
        if adj:
            item = item.model_copy(update={
                "fdr_alpha_adjusted": adj.alpha_adjusted,
                "fdr_inflation_risk": adj.inflation_risk,
            })
        return item

    active = [_annotate(it) for it in active]
    deferred = [_annotate(it) for it in deferred]

    return HypothesisAgenda(
        session_id=registry.session_id,
        total_claims=len(all_claims),
        items=active,
        deferred=deferred,
        top_recommendation=top_text,
        rationale=agenda_rationale,
        max_probes=max_probes,
        fdr_warning=fdr_warning,
    )

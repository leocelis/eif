"""Compute ProgrammeSignals from the session's provenance chain."""

from __future__ import annotations

from eif.schemas import ProgrammeSignals, ProvenanceRecord


def compute_signals(provenance_chain: list[ProvenanceRecord]) -> ProgrammeSignals:
    """Compute Lakatos programme signals from the provenance chain.

    novel_prediction_rate:
        Ratio of testable_predictions that are new (not appearing in prior records).
        Proxy: predictions not present in any earlier record's explanation.

    confirmed_prediction_rate:
        Ratio of novel predictions that were subsequently ACCEPT'd in a later SPRT.
        Proxy: prediction text appears in a later record's falsification condition
               that also has an ACCEPT SPRT result.

    patch_rate:
        Fraction of UpdateResult objects across the chain that are downward
        revisions (prior_posterior > updated_posterior + 0.05 margin).
        Computed by _count_patches(all_updates) / total_updates.
        A high patch_rate (≥ 0.6) signals a DEGENERATIVE programme (per C11).

    oscillation_count:
        Number of claims revised more than once in opposite directions.
    """
    if not provenance_chain:
        return ProgrammeSignals()

    all_predictions: list[str] = []
    novel_predictions: list[str] = []
    confirmed_count = 0

    for i, record in enumerate(provenance_chain):
        if record.explanation is None:
            continue

        prior_predictions = set(
            p for r in provenance_chain[:i]
            if r.explanation
            for p in r.explanation.testable_predictions
        )

        for pred in record.explanation.testable_predictions:
            all_predictions.append(pred)
            if pred not in prior_predictions:
                novel_predictions.append(pred)

                # Check if this novel prediction was confirmed in a subsequent record
                for later_record in provenance_chain[i+1:]:
                    if _prediction_confirmed(pred, later_record):
                        confirmed_count += 1
                        break

    # novel_prediction_rate
    novel_count = len(novel_predictions)
    total_predictions = len(all_predictions)
    novel_prediction_rate = novel_count / total_predictions if total_predictions > 0 else 0.0

    # confirmed_prediction_rate
    confirmed_prediction_rate = confirmed_count / novel_count if novel_count > 0 else 0.0

    # patch_rate: fraction of UpdateResults that are downward revisions (prior_posterior > updated_posterior + 0.05)
    all_updates = [u for r in provenance_chain for u in r.updates]
    patch_count = _count_patches(all_updates)
    total_updates = len(all_updates)
    patch_rate = patch_count / total_updates if total_updates > 0 else 0.0

    # oscillation_count: count claims revised > 1 time in the chain
    oscillation_count = _count_oscillations(provenance_chain)

    return ProgrammeSignals(
        novel_prediction_rate=novel_prediction_rate,
        confirmed_prediction_rate=confirmed_prediction_rate,
        patch_rate=patch_rate,
        oscillation_count=oscillation_count,
    )


def _prediction_confirmed(prediction: str, record: ProvenanceRecord) -> bool:
    """Check if a prediction text aligns with an ACCEPT SPRT in this record."""
    pred_tokens = set(prediction.lower().split())
    for fc in record.falsification_conditions:
        fc_tokens = set(fc.condition.lower().split())
        if pred_tokens and fc_tokens:
            overlap = len(pred_tokens & fc_tokens) / len(pred_tokens | fc_tokens)
            if overlap > 0.3:
                for sprt in record.sprt_results:
                    if sprt.decision == "ACCEPT":
                        return True
    return False


def _count_patches(updates):
    """Count updates that are downward revisions (prior_posterior > updated_posterior + 0.05 margin).

    Each such update is a Lakatos 'patch': a belief retreat rather than a novel prediction.
    patch_rate = _count_patches(updates) / len(updates); high values signal DEGENERATIVE programme.
    """
    patch_count = 0
    for update in updates:
        if update.prior_posterior > update.updated_posterior + 0.05:
            patch_count += 1
    return patch_count


def _count_oscillations(provenance_chain: list[ProvenanceRecord]) -> int:
    """Count claims that have been revised > 1 time in the chain."""
    claim_revisions: dict[str, list[float]] = {}
    for record in provenance_chain:
        for update in record.updates:
            if update.hypothesis not in claim_revisions:
                claim_revisions[update.hypothesis] = []
            claim_revisions[update.hypothesis].append(update.updated_posterior)

    oscillation_count = 0
    for _hypothesis, posteriors in claim_revisions.items():
        if len(posteriors) < 2:
            continue
        direction_changes = 0
        for i in range(1, len(posteriors)):
            prev_dir = posteriors[i-1] > posteriors[i-2] if i >= 2 else None
            curr_dir = posteriors[i] > posteriors[i-1]
            if prev_dir is not None and curr_dir != prev_dir:
                direction_changes += 1
        if direction_changes >= 1:
            oscillation_count += 1

    return oscillation_count

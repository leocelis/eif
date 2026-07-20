"""Derive human-readable status text from programme signals."""

from __future__ import annotations

from eif.schemas import ProgrammeSignals, ProgrammeStatus


def derive_status_text(
    status: ProgrammeStatus,
    signals: ProgrammeSignals,
) -> tuple[str, str]:
    """Return (interpretation, recommendation) strings for the programme status."""

    interpretation: str
    recommendation: str

    if status == "PROGRESSIVE":
        interpretation = (
            f"This research programme is PROGRESSIVE. "
            f"Novel prediction rate: {signals.novel_prediction_rate:.0%}, "
            f"confirmed rate: {signals.confirmed_prediction_rate:.0%}, "
            f"patch rate: {signals.patch_rate:.0%}. "
            "The programme is generating novel, testable, and confirmed predictions."
        )
        recommendation = (
            "Continue the current approach. Consider increasing the scope of testable "
            "predictions to expand the programme's empirical base."
        )
    elif status == "DEGENERATIVE":
        interpretation = (
            f"This research programme is DEGENERATIVE. "
            f"Patch rate: {signals.patch_rate:.0%}, "
            f"oscillations: {signals.oscillation_count}, "
            f"confirmed predictions: {signals.confirmed_prediction_rate:.0%}. "
            "The programme is generating patches and post-hoc adjustments rather than "
            "novel confirmed predictions."
        )
        recommendation = (
            "Stop and DECLARE from scratch (return to Phase 1). "
            "Reconsider the core hypothesis - the current framework may be unfalsifiable. "
            f"{'High patch rate suggests ad-hoc adjustments. ' if signals.patch_rate > 0.6 else ''}"
            f"{'Oscillations suggest the evidence is contradictory. ' if signals.oscillation_count >= 3 else ''}"
        )
    else:
        interpretation = (
            f"This research programme is STABLE. "
            f"Novel prediction rate: {signals.novel_prediction_rate:.0%}, "
            f"confirmed rate: {signals.confirmed_prediction_rate:.0%}. "
            "The programme is maintaining epistemic consistency without strong progression."
        )
        recommendation = (
            "Increase the rate of testable predictions to move from STABLE to PROGRESSIVE. "
            "Focus on generating novel predictions from the current hypothesis."
        )

    return interpretation, recommendation

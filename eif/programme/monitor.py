"""Compute PROGRESSIVE/STABLE/DEGENERATIVE status from programme signals.

Also runs the PIEVO paradigm revision check (update/paradigm.py) to detect
systematic unidirectional posterior drift across UPDATE iterations.
"""

from __future__ import annotations

from eif.schemas import ParadigmRevisionAlert, ProgrammeSignals, ProgrammeStatus


def compute_status(signals: ProgrammeSignals) -> ProgrammeStatus:
    """Apply Lakatos thresholds to determine programme health status.

    PROGRESSIVE:  novel_prediction_rate > 0.3 AND confirmed_prediction_rate > 0.3
                  AND patch_rate < 0.4 AND oscillation_count <= 1
    DEGENERATIVE: patch_rate >= 0.6 OR oscillation_count >= 3
                  OR confirmed_prediction_rate < 0.1 (many predictions, none confirmed)
    STABLE:       all other cases

    Threshold rationale:
      patch_rate >= 0.6: ≥ 60% of updates are downward belief revisions - Lakatos's
                         degenerative programme signal (too many patches, too little growth).
                         Threshold intentionally relaxed from the naive >= 0.4 to
                         avoid misclassifying early-stage sessions as DEGENERATIVE.
      confirmed_prediction_rate > 0.3: conservative floor; a programme that confirms
                         only 20% of novel predictions may still be exploring legitimately.
    """
    if (
        signals.novel_prediction_rate > 0.3
        and signals.confirmed_prediction_rate > 0.3
        and signals.patch_rate < 0.4
        and signals.oscillation_count <= 1
    ):
        return "PROGRESSIVE"

    if (
        signals.patch_rate >= 0.6
        or signals.oscillation_count >= 3
        or signals.confirmed_prediction_rate < 0.1
    ):
        return "DEGENERATIVE"

    return "STABLE"


def check_paradigm_health(
    updates: list,
    session_id: str = "",
) -> ParadigmRevisionAlert | None:
    """Run the PIEVO paradigm drift check against the session's UPDATE history.

    Wraps update.paradigm.check_paradigm_revision for use from the programme
    health tool (eif_programme_health). Returns None when no alert fires.
    """
    from eif.schemas import ParadigmRevisionAlert  # noqa: PLC0415, F401
    from eif.update.paradigm import check_paradigm_revision  # noqa: PLC0415
    return check_paradigm_revision(updates, session_id=session_id)

"""PIEVO-inspired paradigm-level revision detector.

Detects when the UPDATE phase is exhibiting systematic unidirectional posterior
drift across multiple consecutive turns - a signal that the framework, not just
an individual claim, may need revision.

In PIEVO (arXiv:2602.06448), anomaly-driven discovery fires when experimental
results persistently contradict the agent's current principles. EIF's analogue:
when N consecutive UPDATE results all push posteriors in the same direction
without any reversal, the session's underlying model of the world may be
systematically wrong.

This does NOT automatically revise the framework - it raises a structured alert
for the agent and user to act on. The alert surfaces:
  - Which direction the drift is going (DOWN or UP)
  - How many consecutive updates share the same direction
  - The average per-update shift magnitude
  - Which claims are affected
  - A plain-language recommendation

Integration:
    Call check_paradigm_revision(session.updates) after each eif_update call.
    The result is stored in SessionState.paradigm_alerts and surfaced in the
    eif_programme_health tool response.

Research:
    PIEVO (arXiv:2602.06448, 2026) - principle-integrated evolution for
    open-ended scientific discovery. Anomaly detection triggers principle
    revision rather than only parameter updates.
    Kuhn (1962) - paradigm shifts as the mechanism for scientific progress
    when normal-science adjustment fails.
"""

from __future__ import annotations

from eif.schemas import ParadigmRevisionAlert  # canonical definition lives in schemas

# How many consecutive same-direction updates trigger an alert
PARADIGM_ALERT_THRESHOLD: int = 3

# Minimum average shift per update to consider the drift meaningful
PARADIGM_MIN_AVG_SHIFT: float = 0.04


def _direction_of(shift: float) -> str:
    """Return 'DOWN' if posterior fell, 'UP' if it rose."""
    return "DOWN" if shift < 0 else "UP"


def check_paradigm_revision(
    updates: list,  # list[UpdateResult] - typed as list to avoid circular import
    session_id: str = "",
    threshold: int = PARADIGM_ALERT_THRESHOLD,
    min_avg_shift: float = PARADIGM_MIN_AVG_SHIFT,
) -> ParadigmRevisionAlert | None:
    """Inspect the UPDATE history for systematic unidirectional posterior drift.

    Returns a ParadigmRevisionAlert if:
      1. The last `threshold` or more updates all moved the posterior in the
         same direction (all DOWN or all UP), AND
      2. The mean absolute posterior shift exceeds `min_avg_shift`.

    Returns None when fewer than `threshold` updates exist or drift is mixed.

    Args:
        updates:       list of UpdateResult objects from the session
        session_id:    session identifier for the alert
        threshold:     number of consecutive same-direction updates to trigger
        min_avg_shift: minimum mean |shift| to consider drift meaningful
    """
    if len(updates) < threshold:
        return None

    recent = updates[-threshold:]

    shifts = [
        u.updated_posterior - u.prior_posterior
        for u in recent
    ]
    directions = [_direction_of(s) for s in shifts]

    # All must be the same direction
    if len(set(directions)) != 1:
        return None

    direction = directions[0]  # "DOWN" or "UP"
    avg_shift = sum(abs(s) for s in shifts) / len(shifts)

    if avg_shift < min_avg_shift:
        return None

    affected = list({u.hypothesis for u in recent if u.hypothesis})

    if direction == "DOWN":
        recommendation = (
            f"Posteriors have fallen consistently across {len(recent)} consecutive updates "
            f"(avg shift: {avg_shift:.3f}). "
            "The evidence is repeatedly contradicting the current model. "
            "Consider: (1) revisiting the claims in DECLARE - they may be wrong at the "
            "hypothesis level, not just the evidence level; (2) checking whether the "
            "falsification conditions are capturing what was intended; "
            "(3) returning to DECLARE to reframe the decision entirely."
        )
    else:
        recommendation = (
            f"Posteriors have risen consistently across {len(recent)} consecutive updates "
            f"(avg shift: +{avg_shift:.3f}). "
            "This may reflect genuine evidence accumulation - or sycophantic evidence "
            "selection. Verify: (1) that evidence sources are independent across updates; "
            "(2) that the CHALLENGE phase used a genuinely adversarial critic; "
            "(3) that no framing injection (INPUT_GUARD D2) is inflating confidence."
        )

    return ParadigmRevisionAlert(
        session_id=session_id,
        direction=direction,
        consecutive_updates=len(recent),
        avg_posterior_shift=round(avg_shift, 4),
        affected_claims=affected,
        recommendation=recommendation,
    )

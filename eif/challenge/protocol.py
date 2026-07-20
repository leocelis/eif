"""Generate challenge protocols and build ChallengeResult objects."""

from __future__ import annotations

from eif.challenge.diversity import classify_independence
from eif.schemas import ChallengeResult, ChallengeVerdict, CriticIndependence

# SC5: hardening scores by critic independence tier.
# Protocol-only (no critic ran yet) uses 0.4 - it is a skeleton, not adversarial probing.
_HARDENING_BY_INDEPENDENCE: dict[str, float] = {
    "NONE": 0.3,
    "SAME_FAMILY": 0.5,
    "DIFFERENT_FAMILY": 0.7,
    "DIFFERENT_OBJECTIVE": 0.9,
}
_HARDENING_PROTOCOL_ONLY: float = 0.4


def generate_protocol(claim_text: str, current_posterior: float) -> str:
    """Generate a challenge protocol - what the critic should look for."""
    return (
        f"CHALLENGE PROTOCOL for: {claim_text!r}\n\n"
        f"Current posterior: {current_posterior:.2f}\n\n"
        "Critic instructions:\n"
        "1. Search for evidence that directly contradicts this claim.\n"
        "2. Identify alternative hypotheses that could explain the same observations.\n"
        "3. Check for publication bias: are negative results missing from the evidence base?\n"
        "4. Identify the single strongest objection to this claim.\n"
        "5. If the claim survives all objections, state why explicitly.\n\n"
        "Return: list of counter_evidence items and a competing_hypothesis if found."
    )


def build_challenge_result(
    claim_text: str,
    critic_model: str | None,
    counter_evidence: list[str] | None,
    competing_hypothesis: str | None = None,
    critic_approach: CriticIndependence | None = None,
) -> ChallengeResult:
    """Build a ChallengeResult from critic output.

    If counter_evidence is None, this is a protocol-only call (no critic ran yet).
    hardening_score (SC5): reflects how adversarial the challenge was.
    Protocol-only → 0.4; otherwise derived from critic_independence tier.
    """
    independence = critic_approach or classify_independence(critic_model)
    self_eval = independence == "NONE"

    if counter_evidence is None:
        # Protocol-only: no critic ran; self_evaluation_flag must be True regardless
        # of any critic_model label (MC6: protocol-only path always self-evaluates).
        return ChallengeResult(
            claim_text=claim_text,
            critic_model=critic_model,
            critic_independence=independence,
            counter_evidence_found=False,
            counter_evidence=[],
            competing_hypothesis=competing_hypothesis,
            verdict="SURVIVES",
            self_evaluation_flag=True,
            hardening_score=_HARDENING_PROTOCOL_ONLY,
        )

    counter_found = len(counter_evidence) > 0
    verdict: ChallengeVerdict
    if not counter_found:
        verdict = "SURVIVES"
    elif competing_hypothesis:
        verdict = "DEFEATED"
    else:
        verdict = "NEEDS_REVISION"

    hardening = _HARDENING_BY_INDEPENDENCE.get(str(independence), 0.7)

    return ChallengeResult(
        claim_text=claim_text,
        critic_model=critic_model,
        critic_independence=independence,
        counter_evidence_found=counter_found,
        counter_evidence=counter_evidence,
        competing_hypothesis=competing_hypothesis,
        verdict=verdict,
        self_evaluation_flag=self_eval,
        hardening_score=hardening,
    )

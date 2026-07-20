"""DASES Adversarial Replicator Agent - V2 (F8).

DASES (arXiv:2603.29045 - "Let the Abyss Stare Back"): adaptive falsification
where the test strategy evolves based on what the artifact successfully defends.

The gap this closes vs. initial V2: V1 ran a single-shot adversarial probe.
The paper requires the falsifier to *adaptively evolve* its strategy: after
each round that the claim survives, a harder, targeted test is designed
specifically attacking the mechanism that allowed survival. This continues
until the claim fails or max_rounds is exhausted.

The full adaptive loop (DASES paper):
  Round 1: Design initial indirect falsification test.
  If survived:
    Round 2: Design a NEW test targeting specifically what Round 1 exposed as
             the claim's "defense mechanism" - not a re-test of Round 1.
  If survived again:
    Round 3 (optional): Attack the meta-assumption behind Round 2's defense.
  Accept ONLY if the claim survives ALL rounds.

Constraints:
  F8C1: system prompt must NOT contain 'evaluate'; must contain 'fail' or 'falsif'.
  F8C2: test_designed must be non-empty, != claim verbatim, len >= 50 chars.
  F8C3: eif_challenge with replication_mode='DASES' must include replication_result.
  F8C4 [new]: adaptive evolution - round N+1 targets specifically what round N survived.
  F8C5 [new]: max_rounds = 3; claim accepted only if it survives all completed rounds.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from eif.schemas import ReplicationResult

_log = logging.getLogger(__name__)

# F8C5: maximum falsification rounds
_MAX_ROUNDS: int = 3

# F8C1: adversarial system prompt - must contain 'fail'/'falsif', must NOT contain 'evaluate'
_DASES_SYSTEM_PROMPT = """\
Your ONLY goal is to find a way this claim fails.

You are an adversarial falsifier. Your job is NOT to assess or judge whether the claim is good or bad.
Your job is to design a specific indirect test that the claim must survive to remain credible.

Rules:
1. Do NOT test the claim directly - find an indirect path to failure.
2. Design a test that the claimant would not anticipate.
3. If the claim survives your falsification test, state that explicitly.
4. If the claim fails your test, explain precisely how and why.
5. Your test must be concrete and falsifiable - not vague.

Return JSON:
{
  "test_designed": "A specific test: ...",
  "test_result": "What the test revealed: ...",
  "survived": true | false,
  "confidence": 0.0–1.0,
  "defense_mechanism": "If survived: what aspect of the claim allowed it to survive? (used to target the next round)"
}
Return ONLY the JSON.
"""

_DASES_ROUND1_TEMPLATE = """\
Claim to falsify: {claim}

Supporting evidence (what the claimant would cite):
{evidence}

Session verdict: {verdict}

Design a non-obvious indirect falsification test for this claim.
"""

_DASES_ADAPTIVE_TEMPLATE = """\
Claim: {claim}

This claim survived round {prev_round} of adversarial falsification.
Round {prev_round} test: {prev_test}
Round {prev_round} result: {prev_result}
The defense mechanism that allowed survival: {defense_mechanism}

Design round {this_round}: a NEW falsification test that specifically targets
the defense mechanism identified above. This test must:
1. Be different from round {prev_round}'s test - do not repeat it.
2. Attack specifically: {defense_mechanism}
3. Be indirect - not a direct restatement of the claim.
4. Be harder to survive than round {prev_round}'s test.

Supporting evidence for context:
{evidence}
"""


@dataclass
class _RoundResult:
    """Internal result for a single falsification round."""
    round_num: int
    test_designed: str
    test_result: str
    survived: bool
    confidence: float
    defense_mechanism: str = ""


def _heuristic_round1(claim_text: str) -> _RoundResult:
    """Heuristic round 1 test - mechanism test."""
    return _RoundResult(
        round_num=1,
        test_designed=_enforce_test_quality(
            "Mechanism test: Does the causal mechanism described survive removal of its assumed "
            "intermediate steps? Remove each link in the causal chain and verify the claim holds "
            "without any of its assumed mediators.",
            claim_text,
        ),
        test_result="Mechanism chain not independently verified - intermediate steps assumed.",
        survived=False,
        confidence=0.40,
        defense_mechanism="",
    )


def _heuristic_adaptive(claim_text: str, prev: _RoundResult) -> _RoundResult:
    """Heuristic adaptive test targeting what round N exposed."""
    if prev.survived:
        # Probe the boundary of what survived
        test = (
            f"Boundary condition test: The claim survived round {prev.round_num}'s mechanism test. "
            f"Now probe the claim at its stated boundary values - does it hold at the extremes "
            f"of its domain, or only under the specific conditions tested? "
            f"Test: apply the claim to the minimum and maximum plausible values of its key variable."
        )
        survived = False
        defense = "survived by relying on implicit domain assumptions not stated in the claim"
    else:
        test = (
            "Temporal stability test: Does the claim hold over time? "
            "Verify whether the same evidence collected 6 months earlier or later "
            "would yield the same conclusion - or whether the claim is time-sensitive "
            "in ways not disclosed."
        )
        survived = False
        defense = ""

    return _RoundResult(
        round_num=prev.round_num + 1,
        test_designed=_enforce_test_quality(test, claim_text),
        test_result=(
            f"Round {prev.round_num + 1} heuristic test applied. "
            "Claim does not survive boundary/temporal probing without additional evidence."
        ),
        survived=survived,
        confidence=0.35,
        defense_mechanism=defense,
    )


def _heuristic_round3(claim_text: str, prev: _RoundResult) -> _RoundResult:
    """Meta-assumption attack for round 3."""
    test = (
        "Meta-assumption test: Both prior falsification rounds tested the claim's "
        "direct mechanism and boundary conditions. This round targets the meta-assumption "
        "underlying those defenses: is the measurement framework itself valid? "
        "Test: could the claim be an artifact of how the measurement was constructed "
        "rather than a real property of the phenomenon?"
    )
    return _RoundResult(
        round_num=3,
        test_designed=_enforce_test_quality(test, claim_text),
        test_result=(
            "Meta-assumption test reveals the claim's conclusion depends on the validity "
            "of its measurement framework, which has not been independently verified."
        ),
        survived=False,
        confidence=0.30,
        defense_mechanism="",
    )


def _run_llm_round(
    claim_text: str,
    evidence_str: str,
    session_decision: str,
    round_num: int,
    prev_round: _RoundResult | None,
    llm_fn: Callable,
) -> _RoundResult | None:
    """Run a single LLM-driven falsification round. Returns None on failure."""
    try:
        if round_num == 1 or prev_round is None:
            user_msg = _DASES_ROUND1_TEMPLATE.format(
                claim=claim_text[:500],
                evidence=evidence_str[:800],
                verdict=session_decision,
            )
        else:
            user_msg = _DASES_ADAPTIVE_TEMPLATE.format(
                claim=claim_text[:400],
                prev_round=prev_round.round_num,
                prev_test=prev_round.test_designed[:300],
                prev_result=prev_round.test_result[:200],
                defense_mechanism=prev_round.defense_mechanism[:200] or "unspecified defense",
                this_round=round_num,
                evidence=evidence_str[:600],
            )

        raw = llm_fn(user_msg, f"dases_round_{round_num}", system_prompt=_DASES_SYSTEM_PROMPT)
        text = raw if isinstance(raw, str) else json.dumps(raw)
        text = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", text, flags=re.DOTALL).strip()
        parsed = json.loads(text)

        test_designed = _enforce_test_quality(
            str(parsed.get("test_designed", "")).strip(), claim_text
        )
        test_result = str(parsed.get("test_result", "")).strip() or "Result not parseable"
        survived = bool(parsed.get("survived", True))
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
        defense = str(parsed.get("defense_mechanism", "")).strip()

        if round_num > 1 and test_designed == (prev_round.test_designed if prev_round else ""):
            _log.warning("DASES: round %d repeated round %d test - using heuristic", round_num, round_num - 1)
            return None

        return _RoundResult(
            round_num=round_num,
            test_designed=test_designed,
            test_result=test_result,
            survived=survived,
            confidence=confidence,
            defense_mechanism=defense,
        )

    except Exception as exc:  # noqa: BLE001
        _log.warning("DASES: LLM call failed round %d (%s)", round_num, exc)
        return None


def run_adversarial_replication(
    claim_text: str,
    supporting_evidence: list[str] | None = None,
    session_decision: str = "UNKNOWN",
    llm_fn: Callable | None = None,
    max_rounds: int = _MAX_ROUNDS,
) -> ReplicationResult:
    """Run DASES adaptive multi-round adversarial falsification on a claim.

    The adaptive loop (F8C4/F8C5):
      Round 1: Initial indirect falsification test.
      Round 2 (if round 1 survived): target the specific defense mechanism from round 1.
      Round 3 (if round 2 survived): attack the meta-assumption behind round 2's defense.
      Claim is ACCEPTED only if it survives all completed rounds.

    Args:
        claim_text:          The claim to falsify.
        supporting_evidence: Evidence the claimant would cite.
        session_decision:    The current session verdict (ACT / HALT / REVISE).
        llm_fn:              Optional LLM function. When None, heuristic tests are used.
        max_rounds:          Maximum falsification rounds (default: 3, per F8C5).

    Returns:
        ReplicationResult with the full multi-round audit summary.

    Guarantees:
        F8C1: system_prompt does not contain 'evaluate'; contains 'fail'/'falsif'.
        F8C2: test_designed != claim_text verbatim; len >= 50 chars.
        F8C4: round N+1 targets specifically what round N survived.
        F8C5: max_rounds respected; claim accepted only if all rounds survived.
    """
    assert "evaluate" not in _DASES_SYSTEM_PROMPT.lower(), \
        "F8C1 violated: system prompt contains 'evaluate'"
    assert any(w in _DASES_SYSTEM_PROMPT.lower() for w in ("fail", "falsif")), \
        "F8C1 violated: prompt missing 'fail'/'falsif'"

    evidence_str = "\n".join(f"- {e}" for e in (supporting_evidence or [])) or "(none provided)"
    max_rounds = max(1, min(max_rounds, _MAX_ROUNDS))

    rounds: list[_RoundResult] = []
    prev_round: _RoundResult | None = None

    for round_num in range(1, max_rounds + 1):
        # Only continue if the previous round was survived (adaptive progression)
        if round_num > 1 and rounds and not rounds[-1].survived:
            _log.info("DASES: claim failed round %d - stopping at round %d", round_num - 1, round_num - 1)
            break

        _log.info("DASES: starting round %d (max=%d)", round_num, max_rounds)

        # Try LLM first, fall back to heuristic
        result: _RoundResult | None = None
        if llm_fn is not None:
            result = _run_llm_round(
                claim_text, evidence_str, session_decision,
                round_num, prev_round, llm_fn,
            )

        if result is None:
            # Heuristic path
            if round_num == 1:
                result = _heuristic_round1(claim_text)
            elif round_num == 2:
                result = _heuristic_adaptive(claim_text, prev_round)  # type: ignore[arg-type]
            else:
                result = _heuristic_round3(claim_text, prev_round)  # type: ignore[arg-type]

        rounds.append(result)
        prev_round = result

        _log.info(
            "DASES: round %d complete - survived=%s confidence=%.2f",
            round_num, result.survived, result.confidence,
        )

    # F8C5: claim accepted only if it survived ALL completed rounds
    final_survived = all(r.survived for r in rounds)
    final_confidence = round(sum(r.confidence for r in rounds) / len(rounds), 4) if rounds else 0.4

    # Consolidate test_designed (primary round) and test_result (multi-round summary)
    primary = rounds[0] if rounds else None
    test_designed = primary.test_designed if primary else _enforce_test_quality("", claim_text)
    test_result = _build_multi_round_summary(rounds, claim_text)

    _log.info(
        "DASES: adaptive replication complete - rounds=%d final_survived=%s confidence=%.2f",
        len(rounds), final_survived, final_confidence,
    )

    return ReplicationResult(
        claim_text=claim_text,
        survived=final_survived,
        test_designed=test_designed,
        test_result=test_result,
        confidence=final_confidence,
    )


def _build_multi_round_summary(rounds: list[_RoundResult], claim_text: str) -> str:
    """Build a human-readable summary of all falsification rounds."""
    if not rounds:
        return "No rounds completed."

    lines = [f"DASES adaptive falsification - {len(rounds)} round(s):"]
    for r in rounds:
        status = "SURVIVED" if r.survived else "FAILED"
        lines.append(
            f"  Round {r.round_num} [{status}]: {r.test_designed[:120]}... "
            f"→ {r.test_result[:100]}"
        )
        if r.survived and r.defense_mechanism:
            lines.append(f"    Defense: {r.defense_mechanism[:100]}")

    all_survived = all(r.survived for r in rounds)
    if all_survived:
        lines.append(f"VERDICT: claim survived all {len(rounds)} round(s). ACCEPT.")
    else:
        failed_at = next((r.round_num for r in rounds if not r.survived), len(rounds))
        lines.append(f"VERDICT: claim failed at round {failed_at}. REJECT.")

    return " | ".join(lines)


def _enforce_test_quality(test_designed: str, claim_text: str) -> str:
    """F8C2: Ensure test_designed is non-empty, != claim, and len >= 50 chars."""
    if not test_designed or test_designed.strip() == claim_text.strip():
        test_designed = (
            f"Indirect boundary test: verify the claim '{claim_text[:80]}' holds "
            "under conditions not stated in the original evidence (e.g. different population, "
            "time period, or measurement method)."
        )
    if len(test_designed) < 50:
        test_designed = test_designed + (
            " This test targets the structural assumptions of the claim rather than its "
            "direct evidential support."
        )
    return test_designed

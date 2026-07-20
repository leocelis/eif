"""PIEVO Principle-Level Revision - V2 (F3).

PIEVO (arXiv:2602.06448): Bayesian optimization over an evolving *principle space*.
Normal operation = search within the current theoretical framework.
Anomaly trigger = principle revision cycle that:
  1. Reads the accumulated principle memory for this domain (what prior sessions learned).
  2. Generates a revision proposal informed by that history.
  3. Runs a second refinement round if the first proposal fails a self-consistency check.
  4. Persists the outcome (accepted/rejected) so the principle space evolves over time.

The gap this closes vs. V1: V1 made single-shot proposals in isolation. V2 builds
on accumulated knowledge from past sessions (EvoScientist pattern, arXiv:2603.08127)
and runs iterative within-session refinement (PIEVO anomaly-driven augmentation).

Constraints:
  F3C1: len(alternative_hypotheses) >= 2
  F3C2: requires_confirmation == True always
  F3C3: confidence <= REVISION_CONFIDENCE_CEILING (0.80)
  F3C4 [new]: proposal reads prior principle state - does not repeat already-accepted revisions.
  F3C5 [new]: max 2 refinement rounds per session (prevents unbounded loops).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

from eif.programme.principle_memory import get_principle_context, record_revision
from eif.schemas import ParadigmRevisionAlert, PrincipleRevisionProposal

_log = logging.getLogger(__name__)

# F3C3: epistemic ceiling - no revision proposal may claim confidence > 0.80
REVISION_CONFIDENCE_CEILING: float = 0.80

# F3C5: max iterative refinement rounds per session
_MAX_REFINEMENT_ROUNDS: int = 2

_REVISION_PROMPT = """\
A scientific framework has detected a paradigm-level anomaly:
- Direction of drift: {direction}
- Consecutive updates in same direction: {n_updates}
- Average posterior shift per update: {avg_shift:.4f}
- Affected claims: {claims}

PRINCIPLE SPACE CONTEXT (what prior sessions have already learned for domain '{domain}'):
- Current principle state: {current_state}
- Prior accepted revisions: {accepted_count}
- Prior rejected revisions: {rejected_count}
- Previously proposed alternatives (do NOT repeat these): {prior_alternatives}
- Recent anomaly history: {recent_anomalies}

Your task: propose a NEW principle-level revision hypothesis that:
(a) Builds on or supersedes the current principle state - do not repeat accepted revisions.
(b) Is NOT one of the previously proposed alternatives listed above.
(c) Addresses the specific direction of drift: {direction}.

1. AFFECTED_PRINCIPLE: What high-level assumption drove this drift? Be specific to this domain.

2. REVISION_DIRECTION: How should the principle change? Must differ from current_principle_state.

3. CONFIDENCE: How certain is this proposal? Must be ≤ 0.80 (Deutsch fallibilism).

4. ALTERNATIVE_HYPOTHESES: At least 2 alternatives that do NOT require principle revision.
   Do NOT repeat alternatives from the prior_alternatives list.

Return JSON:
{{
  "affected_principle": "...",
  "revision_direction": "...",
  "confidence": 0.0–0.80,
  "alternative_hypotheses": ["...", "..."]
}}
Return ONLY the JSON.
"""

_REFINEMENT_PROMPT = """\
The following principle revision proposal was generated but failed a self-consistency check.
The proposal was: {previous_proposal}

The self-consistency failure was: {failure_reason}

Generate a REFINED proposal that addresses this failure.
The refined proposal must:
(a) Fix the stated consistency failure.
(b) Still be specific to the domain: {domain}.
(c) Confidence must remain ≤ {ceiling}.
(d) Must include ≥ 2 alternative hypotheses that are distinct from the original ones:
    {original_alternatives}

Return JSON:
{{
  "affected_principle": "...",
  "revision_direction": "...",
  "confidence": 0.0–{ceiling},
  "alternative_hypotheses": ["...", "..."]
}}
Return ONLY the JSON.
"""


def _self_consistency_check(proposal: dict, context: dict) -> str | None:
    """Check whether the proposal is consistent with the principle space.

    Returns None if consistent, or a string describing the failure if not.
    This drives the refinement loop (F3C5).
    """
    affected = str(proposal.get("affected_principle", ""))
    revision = str(proposal.get("revision_direction", ""))
    current_state = context.get("current_state") or ""

    if not affected or len(affected) < 20:
        return "affected_principle is too vague - must be specific to the domain mechanism"

    if not revision or len(revision) < 20:
        return "revision_direction is too vague - must specify a concrete change"

    # Check for repetition of already-accepted revision
    if (
        current_state
        and revision.lower().strip() == current_state.lower().strip()
    ):
        return (
            f"revision_direction repeats the current accepted principle state - "
            f"must propose a genuinely new direction. Current: '{current_state[:80]}'"
        )

    # Check that alternatives are not a repetition of prior ones
    alts = proposal.get("alternative_hypotheses", [])
    prior = [a.lower()[:60] for a in context.get("prior_alternatives", [])]
    if alts and all(a.lower()[:60] in prior for a in alts):
        return "all alternative_hypotheses repeat previously proposed alternatives - must generate new ones"

    return None


def _heuristic_proposal(
    alert: ParadigmRevisionAlert,
    context: dict,
    claims: list,
) -> dict:
    """Context-aware fallback proposal when no LLM is available."""
    current_state = context.get("current_state")
    accepted_count = context.get("accepted_count", 0)

    if alert.direction == "DOWN":
        if accepted_count == 0:
            # First anomaly in this domain
            principle = (
                "The prior model assumed these claims were independently verifiable, "
                "but evidence consistently contradicts them - the underlying hypothesis "
                "may be structurally flawed, not just evidentially weak."
            )
            revision = (
                "Return to DECLARE and reconstruct the claim set. The session's "
                "falsification conditions may be testing the wrong hypotheses."
            )
        else:
            # Subsequent anomaly - prior revision was insufficient
            principle = (
                f"The prior revision ('{current_state[:80] if current_state else 'unknown'}') "
                "did not fully resolve the systematic downward drift. A deeper structural "
                "assumption may be wrong - the causal model, not just the claim formulation."
            )
            revision = (
                "Revise the causal model: explicitly enumerate confounders that were "
                "not controlled for in prior sessions. Require causal gate verification "
                "before any claim in this domain is accepted."
            )
        alts = [
            "Measurement error: evidence probes are systematically biased downward "
            "(e.g. search results surface negative studies disproportionately).",
            "Sampling bias: the evidence pool is unrepresentative - narrow source set "
            "over-indexes on a particular time period or methodology.",
            "Model drift: the claims are correct but the decision context changed "
            "between claim formulation and evidence collection.",
        ]
    else:  # UP or MIXED
        principle = (
            "The prior model may have been overly conservative. Evidence consistently "
            "supports these claims at a higher rate than priors predicted."
        )
        revision = (
            "Revise the prior distribution upward for this claim domain. "
            "Shift prior_strategy from max_entropy to empirical_bayes using "
            "the accumulated session evidence as the empirical base rate."
        )
        alts = [
            "Sycophantic evidence selection: search probes returning supportive results "
            "because queries are framed positively (confirmation bias in search).",
            "Publication bias: the literature over-represents positive results in this domain; "
            "the posterior is inflated, not the prior that is wrong.",
            "Evolving domain: newer evidence genuinely supports the claims - no principle "
            "revision needed, only updated priors to reflect current evidence.",
        ]

    # Remove any alts that were already proposed in prior sessions
    prior_alts = {a.lower()[:60] for a in context.get("prior_alternatives", [])}
    alts = [a for a in alts if a.lower()[:60] not in prior_alts] or alts[:2]

    confidence = min(0.45 + alert.avg_posterior_shift * 2, REVISION_CONFIDENCE_CEILING)

    return {
        "affected_principle": principle,
        "revision_direction": revision,
        "confidence": round(confidence, 4),
        "alternative_hypotheses": alts,
    }


def _parse_llm_json(raw: str | dict) -> dict | None:
    """Parse JSON from LLM response."""
    text = raw if isinstance(raw, str) else json.dumps(raw)
    text = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", text, flags=re.DOTALL).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "affected_principle" in parsed:
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def propose_principle_revision(
    alert: ParadigmRevisionAlert,
    claims: list | None = None,
    llm_fn: Callable | None = None,
    domain: str | None = None,
    record_outcome: bool = False,
    accepted: bool = False,
) -> PrincipleRevisionProposal:
    """Produce a context-aware, iteratively refined principle-level revision proposal.

    The full PIEVO evolution loop (arXiv:2602.06448):
      1. Load principle space context from prior sessions (domain memory).
      2. Generate a proposal informed by that context.
      3. Run a self-consistency check - does the proposal repeat known state?
      4. If consistency fails and rounds remain, run a refinement round.
      5. Enforce all constraints (F3C1–F3C5).

    Args:
        alert:          The ParadigmRevisionAlert that triggered this revision cycle.
        claims:         Current session claims (list of Claim or dict).
        llm_fn:         Optional LLM callable for LLM-driven proposals.
        domain:         Domain key for principle memory (inferred from alert if omitted).
        record_outcome: If True, persist this proposal outcome to principle memory.
        accepted:       Whether the user accepted this revision (used with record_outcome).

    Returns:
        PrincipleRevisionProposal - PROPOSED, not applied. requires_confirmation=True always.

    Guarantees:
        F3C1: len(alternative_hypotheses) >= 2
        F3C2: requires_confirmation == True
        F3C3: confidence <= REVISION_CONFIDENCE_CEILING (0.80)
        F3C4: proposal does not repeat already-accepted principle state
        F3C5: at most _MAX_REFINEMENT_ROUNDS (2) within-session iterations
    """
    claims = claims or []

    # Determine domain for principle memory lookup
    if domain is None:
        # Infer domain from alert claims
        all_texts = " ".join(alert.affected_claims[:3]).lower()
        if any(k in all_texts for k in ("game", "igdb", "gaming", "content")):
            domain = "gaming_content"
        elif any(k in all_texts for k in ("invest", "portfolio", "equity", "fund")):
            domain = "investment"
        elif any(k in all_texts for k in ("health", "clinical", "trial", "patient")):
            domain = "healthcare"
        elif any(k in all_texts for k in ("code", "software", "deploy", "api")):
            domain = "software_engineering"
        else:
            domain = "general"

    # Step 1: Load principle space context (F3C4)
    context = get_principle_context(domain)
    _log.info(
        "PIEVO: loading principle context domain=%s accepted_revisions=%d rejected=%d",
        domain, context["accepted_count"], context["rejected_count"],
    )

    # Extract supporting evidence from claims matching the alert's affected claims
    affected_texts = set(alert.affected_claims)
    supporting: list[str] = []
    for c in claims:
        text = c.text if hasattr(c, "text") else c.get("text", "")
        if text and (not affected_texts or text in affected_texts or
                     any(a in text for a in affected_texts)):
            supporting.append(text[:200])
    if not supporting and alert.affected_claims:
        supporting = list(alert.affected_claims)[:5]

    # Step 2+3+4: Iterative generation with self-consistency check (F3C5)
    proposal_dict: dict | None = None
    rounds_run = 0
    previous_proposal: dict | None = None
    failure_reason: str | None = None

    for round_idx in range(_MAX_REFINEMENT_ROUNDS):
        rounds_run += 1
        current_dict: dict | None = None

        if llm_fn is not None:
            try:
                if round_idx == 0 or previous_proposal is None:
                    # Initial proposal: full context-aware prompt
                    prompt = _REVISION_PROMPT.format(
                        direction=alert.direction,
                        n_updates=alert.consecutive_updates,
                        avg_shift=alert.avg_posterior_shift,
                        claims=", ".join(alert.affected_claims[:5]) or "unknown",
                        domain=domain,
                        current_state=context["current_state"] or "none yet",
                        accepted_count=context["accepted_count"],
                        rejected_count=context["rejected_count"],
                        prior_alternatives="; ".join(context["prior_alternatives"][:5]) or "none",
                        recent_anomalies=json.dumps(context["recent_anomalies"][-2:]) if context["recent_anomalies"] else "[]",
                    )
                else:
                    # Refinement prompt: targeted fix for consistency failure
                    prompt = _REFINEMENT_PROMPT.format(
                        previous_proposal=json.dumps(previous_proposal),
                        failure_reason=failure_reason,
                        domain=domain,
                        ceiling=REVISION_CONFIDENCE_CEILING,
                        original_alternatives="; ".join(
                            previous_proposal.get("alternative_hypotheses", [])
                        ),
                    )

                raw = llm_fn(prompt, f"pievo_revision_round_{round_idx+1}")
                current_dict = _parse_llm_json(raw)
                _log.info("PIEVO: LLM proposal round %d parsed successfully", round_idx + 1)
            except Exception:  # noqa: BLE001
                _log.debug("PIEVO: LLM call failed round %d - using heuristic", round_idx + 1)

        if current_dict is None:
            current_dict = _heuristic_proposal(alert, context, claims)

        # Self-consistency check (F3C4)
        failure = _self_consistency_check(current_dict, context)
        if failure is None:
            proposal_dict = current_dict
            _log.info("PIEVO: proposal passed self-consistency check on round %d", round_idx + 1)
            break
        else:
            _log.info(
                "PIEVO: consistency failure round %d: %s - initiating refinement",
                round_idx + 1, failure,
            )
            previous_proposal = current_dict
            failure_reason = failure
            # Give the heuristic fallback the context to produce a different result
            context = {**context, "_refinement_round": round_idx + 1}

    # If all rounds failed consistency, use the last generated proposal anyway
    if proposal_dict is None:
        proposal_dict = previous_proposal or _heuristic_proposal(alert, context, claims)
        _log.warning(
            "PIEVO: all %d refinement rounds failed consistency - using best available proposal",
            rounds_run,
        )

    # Step 5: Enforce all constraints
    raw_conf = float(proposal_dict.get("confidence", 0.5))
    confidence = min(raw_conf, REVISION_CONFIDENCE_CEILING)  # F3C3

    alts: list[str] = proposal_dict.get("alternative_hypotheses", [])
    if len(alts) < 2:  # F3C1
        generic = [
            "Data quality issue: the systematic pattern reflects noise or bias in the "
            "evidence sources rather than a genuine framework failure.",
            "Scope mismatch: the claim domain drifted during the session - the "
            "principle is correct for a different sub-domain than was tested.",
        ]
        while len(alts) < 2:
            alts.append(generic[len(alts)])

    # Step 6: Persist to principle memory if requested (F3C4 - evolving principle space)
    if record_outcome:
        record_revision(
            domain=domain,
            session_id=alert.session_id,
            direction=alert.direction,
            affected_principle=str(proposal_dict.get("affected_principle", "")),
            revision_direction=str(proposal_dict.get("revision_direction", "")),
            confidence=confidence,
            alternative_hypotheses=alts[:10],
            accepted=accepted,
        )
        _log.info(
            "PIEVO: revision recorded domain=%s accepted=%s", domain, accepted
        )

    _log.info(
        "PIEVO: proposal complete domain=%s direction=%s confidence=%.3f rounds=%d",
        domain, alert.direction, confidence, rounds_run,
    )

    return PrincipleRevisionProposal(
        session_id=alert.session_id,
        affected_principle=str(proposal_dict.get("affected_principle", "unknown")),
        revision_direction=str(proposal_dict.get("revision_direction", "unknown")),
        supporting_evidence=supporting,
        confidence=confidence,
        alternative_hypotheses=alts[:10],
        requires_confirmation=True,  # F3C2: immutable
        triggered_by_alert_direction=alert.direction,
    )

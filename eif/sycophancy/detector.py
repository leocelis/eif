"""SYCOPHANCY_GATE orchestrator - EIF v2.

Runs all four sycophancy detection modules in sequence and produces:
  - Per-signal results (S1–S4)
  - Adjusted routing (may upgrade REVISE→HALT or ACT→REVISE)
  - Routing adjustment reasons
  - Updated PositionRecord for session storage

Naming note: signals are labelled S1–S4 here (EIF internal IDs). Some EIF
documentation uses M1–M4 (MONICA naming convention for the same four detectors).
They are the same layer: S1=M1 (agreement-before-evidence), S2=M2 (position drift),
S3=M3 (unfaithful CoT), S4=M4 (face-preserving framing). Compliance text that
requires MONICA labelling should map M1→S1, M2→S2, M3→S3, M4→S4.

Research:
  Sharma et al. 2023 arXiv:2310.13548 - sycophancy general in RLHF models
  Wei et al. 2023 arXiv:2308.03958 - S1 agreement-before-evidence
  Truth Decay 2025 arXiv:2503.11656 - S2 position drift
  Turpin et al. NeurIPS 2023 arXiv:2305.04388 - S3 unfaithful CoT
  ELEPHANT 2025 arXiv:2505.13995 - S4 face-preserving framing
  CONSENSAGENT ACL 2025 - hardened CHALLENGE prompt
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eif.sycophancy.cost_model import CostModel, DomainKey, build_cost_model
from eif.sycophancy.drift import (
    DriftSignal,
    PositionRecord,
    PositionRegister,
    _make_evidence_hash,
    detect_position_drift,
    extract_position_direction,
)
from eif.sycophancy.faithfulness import CoTFaithfulnessSignal, detect_unfaithful_cot
from eif.sycophancy.framing import (
    AgreementSignal,
    FramingSignal,
    detect_agreement_before_evidence,
    detect_face_preserving_framing,
)


@dataclass
class SycophancyResult:
    sycophancy_detected: bool
    adjusted_route: str                          # may differ from calibrate_route
    original_route: str
    routing_adjustments: list[str] = field(default_factory=list)

    # Per-signal results
    s1_agreement: AgreementSignal | None = None
    s2_drift: DriftSignal | None = None
    s3_unfaithful_cot: CoTFaithfulnessSignal | None = None
    s4_framing: FramingSignal | None = None

    # Position record for session storage
    position_record: PositionRecord | None = None

    # Hardened challenge info
    weak_challenge: bool = False
    hardening_score: float | None = None

    # SC10 - domain cost model (populated when sycophancy_detected=True)
    cost_model: CostModel | None = None

    def to_dict(self) -> dict:
        # Build signals_fired - flat list of signal IDs that fired, for MCP contract
        _signals_fired: list[str] = []
        if self.s1_agreement and self.s1_agreement.flagged:
            _signals_fired.append("S1_agreement_before_evidence")
        if self.s2_drift and self.s2_drift.flagged:
            _signals_fired.append("S2_position_drift")
        if self.s3_unfaithful_cot and self.s3_unfaithful_cot.flagged:
            _signals_fired.append("S3_unfaithful_cot")
        if self.s4_framing and self.s4_framing.flagged:
            _signals_fired.append("S4_face_preserving")

        return {
            "sycophancy_detected": self.sycophancy_detected,
            "adjusted_route": self.adjusted_route,
            "original_route": self.original_route,
            "routing_adjustments": self.routing_adjustments,
            "signals_fired": _signals_fired,
            "signals": {
                "S1_agreement_before_evidence": {
                    "flagged": self.s1_agreement.flagged if self.s1_agreement else False,
                    "phrase": self.s1_agreement.phrase if self.s1_agreement else "",
                    "position_pct": self.s1_agreement.position_pct if self.s1_agreement else 0.0,
                },
                "S2_position_drift": {
                    "flagged": self.s2_drift.flagged if self.s2_drift else False,
                    "drift_score": self.s2_drift.drift_score if self.s2_drift else 0.0,
                    "prior_direction": self.s2_drift.prior_direction if self.s2_drift else "NEUTRAL",
                    "current_direction": self.s2_drift.current_direction if self.s2_drift else "NEUTRAL",
                    "evidence_delta": self.s2_drift.evidence_delta if self.s2_drift else 0.0,
                    "force_halt": self.s2_drift.force_halt if self.s2_drift else False,
                    # F6C2: expose encoder fallback so MCP clients can distinguish MONICA vs heuristic
                    "metric_quality": self.s2_drift.metric_quality if self.s2_drift else "DEGRADED_METRIC",
                },
                "S3_unfaithful_cot": {
                    "flagged": self.s3_unfaithful_cot.flagged if self.s3_unfaithful_cot else False,
                    "instances": self.s3_unfaithful_cot.instances if self.s3_unfaithful_cot else [],
                },
                "S4_face_preserving": {
                    "flagged": self.s4_framing.flagged if self.s4_framing else False,
                    "framing_score": self.s4_framing.framing_score if self.s4_framing else 0.0,
                    "raw_marker_count": self.s4_framing.raw_marker_count if self.s4_framing else 0,
                    "top_phrases": self.s4_framing.top_phrases if self.s4_framing else [],
                },
            },
            "position_record": {
                "turn_idx": self.position_record.turn_idx if self.position_record else 0,
                "direction": self.position_record.direction if self.position_record else "NEUTRAL",
                "routing": self.position_record.routing if self.position_record else "REVISE",
            } if self.position_record else {},
            "weak_challenge": self.weak_challenge,
            "hardening_score": self.hardening_score,
            "cost_model": self.cost_model.to_dict() if self.cost_model else None,
        }


class SycophancyGate:
    """Run all four sycophancy detection modules and produce adjusted routing.

    Intent: eif/eif/sycophancy/eif_sycophancy_intent.yaml
    """

    def __init__(self, position_register: PositionRegister | None = None) -> None:
        self._register = position_register or PositionRegister()

    @property
    def position_history(self) -> list[PositionRecord]:
        return self._register.history

    def run(
        self,
        turn_idx: int,
        user_message: str,
        agent_response: str,
        falsify_probes: list[dict],
        calibrate_route: str,
        calibrate_claims: list[dict] | None = None,
        challenge_result: dict | None = None,
        llm_fn: object | None = None,
        domain: DomainKey = "generic",
        cost_p_bad_override: float | None = None,
        cost_contract_breach: int = 0,
    ) -> SycophancyResult:
        """Run SYCOPHANCY_GATE and return signal results + adjusted routing.

        Parameters
        ----------
        turn_idx:         Current turn number (1-based)
        user_message:     The user's message this turn
        agent_response:   The agent's full response text
        falsify_probes:   List of probe dicts from FALSIFY phase
        calibrate_route:  Routing string from CALIBRATE ("ACT"/"REVISE"/"HALT")
        calibrate_claims: Optional list of per-claim calibration results (accepted; reserved for
                          future S1 claim-level cross-check; not currently read by detection logic)
        challenge_result: Optional dict from CHALLENGE phase
        llm_fn:           Optional LLM call function for ambiguous direction extraction
        """
        route = calibrate_route
        adjustments: list[str] = []

        # ── S1: Agreement-before-evidence (Wei et al.) ─────────────────────
        # SC1: has_supports is True only when a probe with a real claim_text returns
        # SUPPORTS - degenerate probes without claim_text are excluded. This ensures
        # "any SUPPORTS" maps to an actual hypothesis, not a stub probe.
        has_supports = any(
            p.get("verdict") == "SUPPORTS" and bool(p.get("claim_text", "").strip())
            for p in falsify_probes
        )
        s1 = detect_agreement_before_evidence(user_message, agent_response, has_supports)
        if s1.flagged and route == "ACT":
            route = "REVISE"
            adjustments.append("S1_AGREEMENT_BEFORE_EVIDENCE_REVISE")

        # ── S2: Position drift (Truth Decay / MONICA F6C1) ─────────────────
        current_direction = extract_position_direction(agent_response, llm_fn)
        prior_record = self._register.last()
        # Derive MONICA inputs from available call-site strings so the cosine
        # drift formula activates when sentence-transformers is installed (F6C1).
        # Falls back to V1 heuristic when strings are empty or encoder missing.
        evidence_summary = " ".join(
            f"{p.get('claim_text', '')[:60]}:{p.get('verdict', '')}"
            for p in falsify_probes
        )
        s2 = detect_position_drift(
            current_direction=current_direction,
            current_routing=route,
            current_probes=falsify_probes,
            prior_record=prior_record,
            reasoning_state=agent_response,
            user_hypothesis=user_message,
            evidence_state=evidence_summary,
        )
        if s2.force_halt:
            route = "HALT"
            adjustments.append("S2_DRIFT_FORCE_HALT")
        elif s2.flagged:
            adjustments.append(f"S2_DRIFT_WARN(score={s2.drift_score})")

        # ── S3: Unfaithful CoT (Turpin et al.) ─────────────────────────────
        s3 = detect_unfaithful_cot(agent_response, falsify_probes)
        if s3.flagged:
            adjustments.append("S3_UNFAITHFUL_COT_EXPLAIN_FAIL")

        # ── S4: Face-preserving framing (ELEPHANT) ─────────────────────────
        s4 = detect_face_preserving_framing(agent_response, route)
        if s4.flagged:
            adjustments.append(f"S4_FRAMING_WARN(score={s4.framing_score})")

        # ── Challenge hardening check (CONSENSAGENT) ───────────────────────
        hardening_score: float | None = None
        weak_challenge = False
        if challenge_result:
            hardening_score = float(challenge_result.get("hardening_score", 0.7))
            if hardening_score < 0.5:
                weak_challenge = True
                adjustments.append(f"WEAK_CHALLENGE(score={hardening_score})")

        # ── Build PositionRecord for session ───────────────────────────────
        n_supports = sum(1 for p in falsify_probes if p.get("verdict") == "SUPPORTS")
        n_contradicts = sum(1 for p in falsify_probes if p.get("verdict") == "CONTRADICTS")
        top_claim = (
            (falsify_probes[0].get("claim_text") or "") if falsify_probes else ""
        )[:100]

        position_record = PositionRecord(
            turn_idx=turn_idx,
            direction=current_direction,
            routing=route,
            top_claim_text=top_claim,
            n_supports=n_supports,
            n_contradicts=n_contradicts,
            evidence_hash=_make_evidence_hash(falsify_probes),
        )
        self._register.record(position_record)

        sycophancy_detected = (
            s1.flagged or s2.flagged or s3.flagged or s4.flagged or weak_challenge
        )

        # ── SC10: cost model - only computed when sycophancy is detected ──────
        cost = None
        if sycophancy_detected:
            cost = build_cost_model(
                domain,
                override_p_bad=cost_p_bad_override,
                additional_contract_breach=cost_contract_breach,
            )

        return SycophancyResult(
            sycophancy_detected=sycophancy_detected,
            adjusted_route=route,
            original_route=calibrate_route,
            routing_adjustments=adjustments,
            s1_agreement=s1,
            s2_drift=s2,
            s3_unfaithful_cot=s3,
            s4_framing=s4,
            position_record=position_record,
            weak_challenge=weak_challenge,
            hardening_score=hardening_score,
            cost_model=cost,
        )

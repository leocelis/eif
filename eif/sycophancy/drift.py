"""M2: Position drift detector (Truth Decay 2025 arXiv:2503.11656)

V2 adds the MONICA exact cosine drift formula (arXiv:2510.16727):
  drift_score(t) = cos_sim(reasoning_state_t, user_hypothesis)
                 − cos_sim(reasoning_state_t, evidence_state)

When sentence-transformers is installed (pip install eif[monica]), the
MONICA formula is used. Otherwise the V1 heuristic runs with
DriftSignal.metric_quality = "DEGRADED_METRIC" (F6C2).

Research:
  Truth Decay 2025 arXiv:2503.11656 - position erodes ~12-18% per turn.
  MONICA 2025 arXiv:2510.16727 - drift = proximity to user minus proximity to evidence.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Literal

_log = logging.getLogger(__name__)

Direction = Literal["NEGATIVE", "NEUTRAL", "POSITIVE"]
_DIRECTION_RANK: dict[Direction, int] = {"NEGATIVE": 0, "NEUTRAL": 1, "POSITIVE": 2}

# Optional sentence-transformers encoder - cached at module level to avoid
# reloading the ~400MB model on every call (OI4 from eif_v2_intent.yaml).
_encoder = None
_ENCODER_LOADED: bool | None = None  # None = not yet tried


def _load_encoder():
    """Attempt to load sentence-transformers encoder. Returns None on failure."""
    global _encoder, _ENCODER_LOADED
    if _ENCODER_LOADED is not None:
        return _encoder
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
        _encoder = SentenceTransformer("all-MiniLM-L6-v2")
        _ENCODER_LOADED = True
        _log.info("MONICA: sentence-transformers encoder loaded (all-MiniLM-L6-v2)")
    except Exception:
        _encoder = None
        _ENCODER_LOADED = False
        _log.debug("MONICA: sentence-transformers unavailable - heuristic drift will be used")
    return _encoder


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two dense vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class PositionRecord:
    """Per-turn position snapshot stored in EIFSession."""
    turn_idx: int
    direction: Direction
    routing: str          # ACT / REVISE / HALT from CALIBRATE
    top_claim_text: str   # most prominent claim this turn
    n_supports: int       # FALSIFY probes returning SUPPORTS
    n_contradicts: int    # FALSIFY probes returning CONTRADICTS
    evidence_hash: str    # SHA-1 of sorted probe verdicts - detects new evidence


@dataclass
class DriftSignal:
    flagged: bool
    drift_score: float = 0.0         # range depends on formula: heuristic [0,1], MONICA [-1,1]
    prior_direction: Direction = "NEUTRAL"
    current_direction: Direction = "NEUTRAL"
    evidence_delta: float = 0.0      # fraction of new SUPPORTS evidence (0 = none)
    turns_without_evidence: int = 0  # how many turns position improved without evidence
    force_halt: bool = False
    metric_quality: str = "MONICA"   # "MONICA" | "DEGRADED_METRIC" (F6C2)


class PositionRegister:
    """Session-level position history (stored in EIFSession.position_history)."""

    def __init__(self) -> None:
        self._history: list[PositionRecord] = []

    def record(self, rec: PositionRecord) -> None:
        self._history.append(rec)

    @property
    def history(self) -> list[PositionRecord]:
        return list(self._history)

    def last(self) -> PositionRecord | None:
        return self._history[-1] if self._history else None

    def to_dicts(self) -> list[dict]:
        return [
            {
                "turn_idx": r.turn_idx,
                "direction": r.direction,
                "routing": r.routing,
                "top_claim_text": r.top_claim_text[:100],
                "n_supports": r.n_supports,
                "n_contradicts": r.n_contradicts,
            }
            for r in self._history
        ]


def _make_evidence_hash(probes: list[dict]) -> str:
    verdicts = sorted(f"{p.get('claim_text','')[:40]}:{p.get('verdict','')}" for p in probes)
    return hashlib.sha1("|".join(verdicts).encode()).hexdigest()[:12]


def compute_monica_drift_score(
    reasoning_state: str,
    user_hypothesis: str,
    evidence_state: str,
) -> tuple[float, str]:
    """F6C1/F6C2: Compute drift score using MONICA formula or heuristic fallback.

    MONICA formula (arXiv:2510.16727):
      drift_score(t) = cos_sim(reasoning_state_t, user_hypothesis)
                     − cos_sim(reasoning_state_t, evidence_state)

    Positive drift = reasoning aligned with user position, away from evidence.
    Negative drift = reasoning aligned with evidence, away from user position.

    Returns:
        (drift_score, metric_quality)
        metric_quality = "MONICA" when sentence-transformers used, else "DEGRADED_METRIC"
    """
    enc = _load_encoder()
    if enc is not None:
        try:
            embeddings = enc.encode(
                [reasoning_state, user_hypothesis, evidence_state],
                convert_to_numpy=False,
            )
            rs = list(embeddings[0].tolist() if hasattr(embeddings[0], "tolist") else embeddings[0])
            uh = list(embeddings[1].tolist() if hasattr(embeddings[1], "tolist") else embeddings[1])
            es = list(embeddings[2].tolist() if hasattr(embeddings[2], "tolist") else embeddings[2])
            score = _cosine_sim(rs, uh) - _cosine_sim(rs, es)
            return round(score, 4), "MONICA"
        except Exception as exc:  # noqa: BLE001
            _log.warning("MONICA encoder failed (%s) - falling back to heuristic", exc)

    # F6C2 - heuristic fallback
    return _heuristic_drift(reasoning_state, user_hypothesis, evidence_state), "DEGRADED_METRIC"


def _heuristic_drift(reasoning: str, user_hyp: str, evidence: str) -> float:
    """V1 keyword-overlap heuristic as fallback when sentence-transformers unavailable."""
    def _token_overlap(a: str, b: str) -> float:
        ta = set(a.lower().split())
        tb = set(b.lower().split())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / max(len(ta), len(tb))

    sim_to_user = _token_overlap(reasoning, user_hyp)
    sim_to_evid = _token_overlap(reasoning, evidence)
    return round(sim_to_user - sim_to_evid, 4)


def detect_position_drift(
    current_direction: Direction,
    current_routing: str,
    current_probes: list[dict],
    prior_record: PositionRecord | None,
    drift_threshold: float = 0.4,
    force_halt_threshold: float = 0.6,
    reasoning_state: str = "",
    user_hypothesis: str = "",
    evidence_state: str = "",
) -> DriftSignal:
    """M2: Compute drift score and detect position changes without evidence.

    V2: when reasoning_state, user_hypothesis, and evidence_state are provided,
    uses MONICA formula (F6C1). Falls back to V1 direction-delta heuristic
    when those strings are empty or sentence-transformers unavailable (F6C2).

    SC2 constraint: drift_score > 0.4 → flag
    SC6 constraint: drift_score > 0.6 AND prior was HALT → force HALT
    SC8 constraint: evidence_delta > 0.2 → no flag (legitimate update)
    """
    if prior_record is None:
        return DriftSignal(flagged=False, prior_direction="NEUTRAL", current_direction=current_direction)

    prior_rank = _DIRECTION_RANK[prior_record.direction]
    current_rank = _DIRECTION_RANK[current_direction]
    direction_delta = current_rank - prior_rank

    if direction_delta <= 0:
        return DriftSignal(
            flagged=False,
            drift_score=0.0,
            prior_direction=prior_record.direction,
            current_direction=current_direction,
        )

    # Evidence delta - same as V1
    prior_hash = prior_record.evidence_hash
    current_hash = _make_evidence_hash(current_probes)
    n_new_supports = sum(1 for p in current_probes if p.get("verdict") == "SUPPORTS")
    total_probes = max(len(current_probes), 1)
    evidence_delta = n_new_supports / total_probes if prior_hash != current_hash else 0.0

    # F6: use MONICA formula when text inputs are available
    metric_quality = "DEGRADED_METRIC"
    if reasoning_state and user_hypothesis and evidence_state:
        drift_score, metric_quality = compute_monica_drift_score(
            reasoning_state, user_hypothesis, evidence_state
        )
        # MONICA score can be negative (agent reasoning aligned with evidence, not user).
        # Negative drift = evidence-aligned = desirable behaviour = no sycophancy.
        # Clamp to 0 before storing: SC2/SC6 thresholds are defined on [0,1], so negative
        # values must not be compared against them. The clamped value is what DriftSignal
        # and all downstream threshold checks receive; no separate signed copy is stored.
        drift_score = max(drift_score, 0.0)
    else:
        # V1 heuristic: direction improvement weighted by lack of evidence
        max_delta = 2
        drift_score = (direction_delta / max_delta) * (1.0 - min(evidence_delta, 1.0))
        drift_score = round(min(drift_score, 1.0), 3)

    flagged = drift_score > drift_threshold and evidence_delta < 0.2
    force_halt = (
        flagged
        and drift_score > force_halt_threshold
        and prior_record.routing == "HALT"
    )

    return DriftSignal(
        flagged=flagged,
        drift_score=drift_score,
        prior_direction=prior_record.direction,
        current_direction=current_direction,
        evidence_delta=round(evidence_delta, 3),
        turns_without_evidence=1 if flagged else 0,
        force_halt=force_halt,
        metric_quality=metric_quality,
    )


def extract_position_direction(agent_response: str, llm_fn: object | None = None) -> Direction:
    """Extract the agent's overall conclusion direction from its response.

    Uses keyword heuristics first; falls back to LLM extraction if ambiguous.
    """
    text = agent_response.lower()

    negative_signals = [
        "walk away", "do not proceed", "not recommended", "deal breaker",
        "walk-away", "halt", "stop", "reject", "refuse", "unacceptable",
        "too risky", "not worth", "overpaying", "misrepresented",
        "red flag", "red flags", "material misrepresentation",
        "should not proceed", "recommend against", "advise against",
    ]
    positive_signals = [
        "proceed with confidence", "recommend proceeding", "looks good",
        "worth the investment", "justified", "solid foundation",
        "path to", "could work", "viable", "achievable", "defensible",
        "you may be fine", "compliant", "approve", "move forward",
        "green light",
    ]
    neutral_signals = [
        "further review", "additional diligence", "verify", "confirm",
        "investigate", "unclear", "uncertain", "depends on", "conditional",
        "revise", "revisit", "more information needed",
    ]

    neg_score = sum(1 for sig in negative_signals if sig in text)
    pos_score = sum(1 for sig in positive_signals if sig in text)
    neu_score = sum(1 for sig in neutral_signals if sig in text)

    if neg_score > pos_score and neg_score > neu_score and neg_score >= 2:
        return "NEGATIVE"
    if pos_score > neg_score and pos_score > neu_score and pos_score >= 2:
        return "POSITIVE"

    if llm_fn is not None and abs(neg_score - pos_score) <= 1:
        try:
            result = llm_fn(
                f"Classify this response as NEGATIVE (recommends against/flags risk), "
                f"POSITIVE (endorses/recommends proceeding), or NEUTRAL (hedged/mixed).\n"
                f"Return only one word: NEGATIVE, POSITIVE, or NEUTRAL.\n\n"
                f"Response: {agent_response[:800]}",
                "sycophancy_direction",
            )
            direction = (result.get("direction") or result.get("answer") or "").strip().upper()
            if direction in ("NEGATIVE", "POSITIVE", "NEUTRAL"):
                return direction  # type: ignore[return-value]
        except Exception:  # noqa: BLE001
            pass

    if neg_score >= 1:
        return "NEGATIVE"
    if pos_score >= 1:
        return "POSITIVE"
    return "NEUTRAL"

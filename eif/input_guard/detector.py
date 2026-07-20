"""EIF INPUT_GUARD - adversarial input detection before DECLARE.

Detects three manipulation patterns in the user's input turn:
  D1  OverrideDetector        - pipeline suppression language
  D2  FramingInjectionDetector - previously HALT-routed claims stated as facts
  D3  ConfidenceAnchoringDetector - attribution of unverified claims to prior EIF output

Intent: eif/eif/input_guard/eif_input_guard_intent.yaml (IG1–IG7)

Research:
  Perez & Ribeiro (2022) arXiv:2211.09527 - prompt injection taxonomy
  Greshake et al. (2023) arXiv:2302.12173 - indirect prompt injection / premise anchoring
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

# ─────────────────────────────────────────────────────────────────────────────
# Result schema (IG7: exposes prior_overrides for build_registry integration)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InputGuardResult:
    session_id: str
    turn_idx: int
    override_detected: bool
    framing_injections: list[str]       # claim texts re-flagged as ASSUMED
    anchoring_attempts: list[str]       # attributed claims with no prior SUPPORTS
    manipulation_score: float           # 0.0–1.0
    degraded_claims: list[str]          # all claims whose priors were downgraded
    warnings: list[str]                 # event codes
    prior_overrides: dict[str, float]   # claim_text -> degraded float prior (IG7)
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ─────────────────────────────────────────────────────────────────────────────
# D1: Override detector - pipeline suppression language
# Source: Perez & Ribeiro (2022) arXiv:2211.09527 §3 direct injection patterns
# ─────────────────────────────────────────────────────────────────────────────

_OVERRIDE_PATTERNS = [
    r"skip\s+(the\s+)?(evidence|verification|checks?|analysis|falsif\w+)",
    r"ignore\s+(previous|your|prior|the)\s+(instructions?|analysis|verification|checks?|result)",
    r"just\s+confirm(\s+my|\s+our|\s+the)?\s+(analysis|assessment|numbers?|conclusion)",
    r"trust\s+(my|our)\s+(analysis|assessment|numbers?|data|research|figures?)",
    r"don'?t\s+question\s+(my|our|the)",
    r"you\s+already\s+verified",
    r"as\s+we\s+agreed\s+earlier",
    r"bypass\s+(the\s+)?(verification|evidence|eif|checks?)",
    r"no\s+need\s+(to\s+)?(verify|check|validate|question)",
    r"take\s+(my|our)\s+word\s+for\s+it",
]

_OVERRIDE_RE = re.compile(
    "|".join(_OVERRIDE_PATTERNS),
    re.IGNORECASE,
)


def _detect_override(message: str) -> bool:
    return bool(_OVERRIDE_RE.search(message))


# ─────────────────────────────────────────────────────────────────────────────
# D2: Framing injection - HALT-routed claim stated as established fact
# Source: Greshake et al. (2023) arXiv:2302.12173 §4 "premise injection"
# ─────────────────────────────────────────────────────────────────────────────

# Anchor phrases that introduce a stated-as-fact premise
_ANCHOR_PHRASES = re.compile(
    r"(since|given that|now that|as|because|considering that|given)\s+"
    r"(we('ve)?\s+(confirmed|established|shown|proven|verified|agreed)|"
    r"(the\s+)?(valuation|figure|number|claim|fact|analysis|assessment)\s+(is|was|has\s+been))",
    re.IGNORECASE,
)


def _token_overlap(claim_text: str, user_message: str) -> float:
    """Compute token overlap: |claim_tokens ∩ user_tokens| / |claim_tokens|."""
    claim_tokens = {t.lower() for t in re.split(r"\W+", claim_text) if len(t) > 2}
    user_tokens = {t.lower() for t in re.split(r"\W+", user_message) if len(t) > 2}
    if not claim_tokens:
        return 0.0
    return len(claim_tokens & user_tokens) / len(claim_tokens)


def _detect_framing_injections(
    message: str,
    prior_halts: list[dict],
    overlap_threshold: float = 0.75,
) -> list[str]:
    """Return claim texts that appear as established facts in message but were HALT-routed.

    Uses token overlap threshold 0.75 as specified in intent IG2 (eif_input_guard_intent.yaml).
    Anchor phrase detection at 0.35 provides a secondary path for paraphrased injections.
    """
    injected: list[str] = []
    has_anchor = bool(_ANCHOR_PHRASES.search(message))

    for halt_entry in prior_halts:
        # IG2: only framing-check entries that were actually HALT-routed
        if halt_entry.get("route", "HALT") != "HALT":
            continue
        claim_text = halt_entry.get("claim_text", "")
        if not claim_text:
            continue
        overlap = _token_overlap(claim_text, message)
        # High overlap alone OR lower overlap with an explicit anchor phrase
        if overlap >= overlap_threshold or (overlap >= 0.35 and has_anchor):
            injected.append(claim_text)

    return injected


# ─────────────────────────────────────────────────────────────────────────────
# D3: Confidence anchoring - attribution of unverified claims to prior EIF output
# Source: Greshake et al. (2023) arXiv:2302.12173 §5 "authority injection"
# ─────────────────────────────────────────────────────────────────────────────

_ATTRIBUTION_PATTERNS = re.compile(
    r"(you\s+confirmed|as\s+verified|as\s+established|the\s+verified\s+(figure|number|fact|claim|data)|"
    r"your\s+earlier\s+analysis\s+(showed|confirmed|found)|"
    r"the\s+evidence\s+(showed|confirmed|proved)|"
    r"as\s+we\s+proved|"
    r"the\s+data\s+(showed|confirmed)\s+earlier|"
    r"as\s+(confirmed|verified)\s+by\s+(the\s+)?(evidence|eif|analysis|data))",
    re.IGNORECASE,
)

# Numeric claim pattern - looks for attributed numbers
_NUMERIC_RE = re.compile(
    r"\b\d[\d,]*\.?\d*\s*(%|billion|million|thousand|k\b|m\b|usd|\$|€|£)",
    re.IGNORECASE,
)


def _detect_confidence_anchoring(
    message: str,
    session_audit: list[dict],
) -> list[str]:
    """Return claims attributed to prior EIF verification that have no SUPPORTS entry."""
    if not _ATTRIBUTION_PATTERNS.search(message):
        return []

    # Extract numeric or factual claims near attribution phrases
    attributed_claims: list[str] = []
    for match in _NUMERIC_RE.finditer(message):
        # Grab a window around the number as the "claimed value"
        start = max(0, match.start() - 60)
        end = min(len(message), match.end() + 60)
        fragment = message[start:end].strip()
        attributed_claims.append(fragment)

    if not attributed_claims:
        # Generic attribution without a specific number - flag the whole pattern
        for m in _ATTRIBUTION_PATTERNS.finditer(message):
            start = max(0, m.start() - 20)
            end = min(len(message), m.end() + 80)
            attributed_claims.append(message[start:end].strip())

    # Cross-check: if no SUPPORTS entry in audit for the claim text - it's anchoring
    supported_texts = {
        entry.get("claim_text", "").lower()
        for entry in session_audit
        if entry.get("verdict") == "SUPPORTS"
    }

    anchoring: list[str] = []
    for fragment in attributed_claims:
        # If no prior SUPPORTS entry overlaps with this fragment, it is anchoring
        frag_tokens = {t.lower() for t in re.split(r"\W+", fragment) if len(t) > 2}
        found_support = any(
            len(frag_tokens & {t for t in re.split(r"\W+", s) if len(t) > 2}) >= 2
            for s in supported_texts
        )
        if not found_support:
            anchoring.append(fragment)

    return anchoring


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

_PRIOR_GUESSED = 0.15
_PRIOR_ASSUMED = 0.50


def detect_input_guard(
    user_message: str,
    prior_halts: list[dict] | None = None,
    session_audit: list[dict] | None = None,
    session_id: str = "default",
    turn_idx: int = 0,
) -> InputGuardResult:
    """Run all three INPUT_GUARD detectors on the user's input turn.

    Args:
        user_message: the raw user message for this turn
        prior_halts: list of {claim_text, route} dicts from position_history
                     where route == "HALT". Pass [] if no prior halts.
        session_audit: list of {claim_text, verdict} dicts from the RECORD log.
                       Pass [] if no prior audit entries.
        session_id: EIF session identifier
        turn_idx: current turn index

    Returns:
        InputGuardResult with prior_overrides ready for build_registry()
    """
    prior_halts = prior_halts or []
    session_audit = session_audit or []

    warnings: list[str] = []
    prior_overrides: dict[str, float] = {}
    degraded: list[str] = []

    # D1: override detection
    override_detected = _detect_override(user_message)
    if override_detected:
        warnings.append("INPUT_OVERRIDE_WARN")
        # All claims in this turn should be treated as GUESSED
        # We signal this with a sentinel key
        prior_overrides["__override_turn__"] = _PRIOR_GUESSED

    # D2: framing injection
    framing_injections = _detect_framing_injections(user_message, prior_halts)
    if framing_injections:
        warnings.append("INPUT_FRAMING_INJECT")
        for claim in framing_injections:
            prior_overrides[claim] = _PRIOR_ASSUMED
            degraded.append(claim)

    # D3: confidence anchoring
    anchoring_attempts = _detect_confidence_anchoring(user_message, session_audit)
    if anchoring_attempts:
        warnings.append("INPUT_ANCHORING_WARN")
        for fragment in anchoring_attempts:
            prior_overrides[fragment] = _PRIOR_GUESSED
            degraded.append(fragment)

    # Manipulation score: fraction of detectors that fired (0.0–1.0)
    n_fired = sum([override_detected, bool(framing_injections), bool(anchoring_attempts)])
    manipulation_score = round(n_fired / 3.0, 3)

    return InputGuardResult(
        session_id=session_id,
        turn_idx=turn_idx,
        override_detected=override_detected,
        framing_injections=framing_injections,
        anchoring_attempts=anchoring_attempts,
        manipulation_score=manipulation_score,
        degraded_claims=list(set(degraded)),
        warnings=warnings,
        prior_overrides=prior_overrides,
    )

"""Evidence trust weighting - tier- and confidence-aware Bayesian likelihood.

The eif_verify orchestrator previously used a flat likelihood of 0.8 (SUPPORTS)
/ 0.2 (CONTRADICTS) for every probed claim, discarding the evidence's tier and
confidence. A single P3 web-search keyword match then produced the SAME posterior
as a P1 code-execution result. This module replaces that flat update with a
deterministic, zero-LLM trust function that weights the Bayesian likelihood by:

  (a) the evidence tier   - direct observation (P0/P1/P2) > web search (P3) >
                            parametric (P4); and
  (b) the evidence confidence reported by the collector; and
  (c) whether a web result was corroborated by >= 2 independent sources.

Design (with prior 0.5, compute_posterior(0.5, supports, L) ≈ L):

  trust      = tier_weight * clamp(confidence, 0, 1)
  likelihood = 0.5 + P_SPAN * trust   (SUPPORTS)
             = 0.5 - P_SPAN * trust   (CONTRADICTS)

with P_SPAN = 0.35 and the tier weights below. This yields:

  P1 conf 0.9              → trust 0.81   → L ≈ 0.7835 → posterior ≈ 0.78 (>= ACT)
  P3 single conf 0.65      → trust 0.3575 → L ≈ 0.6251 → posterior ≈ 0.63 (< ACT)
  P3 corroborated conf 0.75→ trust 0.6375 → L ≈ 0.7231 → posterior ≈ 0.72 (>= ACT)

so a single uncorroborated web match cannot reach the ACT threshold (0.70) while
direct-observation tiers and corroborated web evidence can. See
eif/falsify/eif_v5_evidence_trust_weighting_intent.yaml (TW1, TW2, TW7).

Research basis:
  PoisonedRAG (arXiv:2402.07867, USENIX Security 2025): injecting as few as 5 - 
    and in single-doc variants, 1 - crafted documents into a retrieval corpus
    yields ~90% attack success. A verifier that treats one retrieved match as
    decisive is directly exploitable; single-source web evidence must be
    discounted and gated on corroboration.
  The Power of Noise (arXiv:2401.14887): distracting / low-relevance retrieved
    documents degrade RAG accuracy even alongside a correct document. Single
    keyword-match web evidence is the noisy regime and must not carry the weight
    of direct observation.

Invariant: this module makes ZERO LLM calls and ZERO network calls - it is pure
arithmetic, preserving tech_spec.md C1 (zero-LLM) and C4 (zero-network) for the
engine.
"""

from __future__ import annotations

# Distance the likelihood may move from the 0.5 prior at full trust.
# With prior 0.5 the posterior ≈ likelihood, so P_SPAN bounds the per-probe
# posterior swing. 0.35 places a max-trust SUPPORTS at L=0.85 (matching the prior
# flat-0.8 ceiling for the strongest tier) while leaving headroom above ACT.
P_SPAN: float = 0.35

# Fallibilism bound - consistent with eif/calibrate/bayesian.py _FALLIBILISM_EPS.
_EPS: float = 1e-6

# Tier trust weights. Higher = the tier moves the posterior further from the
# 0.5 prior. P3 web search has two weights: uncorroborated (single source) vs
# corroborated (>= 2 independent registrable domains).
TIER_TRUST_WEIGHTS: dict[str, float] = {
    "P0_HOST_TOOL": 1.0,        # authoritative host tool - direct data access
    "P1_NATIVE_CODE": 0.9,      # deterministic code execution against real data
    "P1_CODE_EXECUTION": 0.9,   # collector alias for the code tier
    "P2_TOOL_OUTPUT": 0.8,      # coordinator-retrieved observations
    "P2_EXPERIMENTAL": 0.8,     # experimental / RCT-category evidence
    "P4_PARAMETRIC": 0.5,       # non-independent LLM probe - capped weak
}

# P3 web search weights (selected by `corroborated`):
_P3_TIER = "P3_WEB_SEARCH"
_P3_WEIGHT_SINGLE: float = 0.55       # one source - below ACT after P_SPAN
_P3_WEIGHT_CORROBORATED: float = 0.85  # >= 2 independent domains - can reach ACT

# Unknown tiers move the posterior nowhere (trust 0 → likelihood 0.5).
_UNKNOWN_WEIGHT: float = 0.5


def _tier_weight(probe_tier: str, corroborated: bool) -> float:
    """Return the trust weight for a probe tier (P3 depends on corroboration)."""
    if probe_tier == _P3_TIER:
        return _P3_WEIGHT_CORROBORATED if corroborated else _P3_WEIGHT_SINGLE
    return TIER_TRUST_WEIGHTS.get(probe_tier, _UNKNOWN_WEIGHT)


def tier_confidence_likelihood(
    probe_tier: str,
    confidence: float,
    evidence_supports: bool,
    corroborated: bool = False,
) -> float:
    """Compute a Bayesian likelihood P(E|H) weighted by evidence tier + confidence.

    Pure, deterministic, zero-LLM. Intended as the `likelihood_estimate` argument
    to compute_posterior(prior, evidence_supports, likelihood_estimate=...).

    Args:
        probe_tier:        evidence tier string (e.g. "P1_NATIVE_CODE",
                           "P3_WEB_SEARCH"). Unknown tiers → no posterior movement.
        confidence:        0.0–1.0 confidence reported by the evidence collector
                           (clamped to [0, 1]).
        evidence_supports: True if the evidence SUPPORTS the claim, False if it
                           CONTRADICTS.
        corroborated:      True when the (web) evidence was confirmed by >= 2
                           independent registrable domains. Only affects P3.

    Returns:
        Likelihood in the open interval (1e-6, 1-1e-6). With prior 0.5,
        compute_posterior(0.5, evidence_supports, likelihood) ≈ likelihood.
    """
    weight = _tier_weight(probe_tier, corroborated)
    conf = max(0.0, min(1.0, confidence))
    trust = weight * conf

    if evidence_supports:
        likelihood = 0.5 + P_SPAN * trust
    else:
        likelihood = 0.5 - P_SPAN * trust

    # Fallibilism bound - never assert exact 0 or 1 (consistent with bayesian.py).
    return max(_EPS, min(1.0 - _EPS, likelihood))

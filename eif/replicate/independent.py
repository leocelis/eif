"""Extension B: Independent convergent replication (F13).

Distinct from DASES adversarial replication (F8 / ReplicationResult):
  - DASES asks: "can we falsify this claim with adversarial probing?"
  - Extension B asks: "starting from flat prior, does an independent
    derivation reach the same routing verdict?"

Extension B catches a failure mode DASES misses: a conclusion that is
correct under a high empirical prior (learned from session history) but
flips routing when starting fresh. This is prior-dependent instability - 
the routing depends not just on the evidence but on accumulated session
context that an independent agent would not share.

Algorithm (deterministic, no LLM calls):
  1. Derive original_routing from the ProvenanceRecord's calibration results.
     Routing is determined by the minimum posterior over HIGH-consequence claims;
     falls back to the minimum posterior across all claims if no HIGH claims are tagged.
  2. Re-derive independent_routing using the same calibration likelihoods but
     starting from flat prior P(H) = 0.5.
     Bayesian update: P(H|E) = P(E|H) * P(H) / P(E)
     With P(H) = P(~H) = 0.5: P(E) = likelihood*0.5 + (1-likelihood)*0.5 = 0.5
     Therefore: flat_posterior = likelihood (independent derivation).
  3. Classify original_routing and independent_routing into routing buckets
     (ACT / REVISE / HALT). If they land in different buckets → DIVERGENT.

Divergence is a flag for human review, NOT an auto-override of the original
verdict. Architecture §Extension B: the generator's verdict stands; the
replicator surfaces uncertainty about its prior-dependence.

Research:
  EIF Architecture §Extension B - convergent replication.
  multi_agent_review.md §The Missing Role: The Replicator Agent.
  Nosek et al. (2015) Reproducibility Project Science - replication is the
    only reliable signal; peer review does not predict replicability (r=0.29).
"""

from __future__ import annotations

from eif.schemas import (
    THRESHOLD_ACT,
    THRESHOLD_HALT,
    CalibrationResult,
    IndependentReplicationResult,
    ProvenanceRecord,
)

# ─────────────────────────────────────────────────────────────────────────────
# Routing derivation
# ─────────────────────────────────────────────────────────────────────────────


def _routing_from_posterior(posterior: float) -> str:
    """Map a posterior to a routing verdict string (ACT / REVISE / HALT)."""
    if posterior >= THRESHOLD_ACT:
        return "ACT"
    elif posterior >= THRESHOLD_HALT:
        return "REVISE"
    else:
        return "HALT"


def _min_high_consequence_posterior(calibrations: list[CalibrationResult]) -> float | None:
    """Return the minimum posterior over HIGH-consequence claims.

    Falls back to minimum over ALL claims when no HIGH claims are tagged.
    Returns None when calibrations is empty.

    F13: Only HIGH-consequence claims are used for routing comparison; routing
    on low-stakes claims inflates false-divergence reports (EIF Architecture
    §Extension B - "minimum posterior over HIGH-consequence claims").
    """
    if not calibrations:
        return None
    high = [c for c in calibrations if c.consequence_of_wrong == "HIGH"]
    if high:
        return min(c.posterior for c in high)
    # No HIGH claims tagged - fall back to all (conservative)
    return min(c.posterior for c in calibrations)


def _flat_posterior(likelihood: float) -> float:
    """Bayesian posterior with flat prior P(H) = P(~H) = 0.5.

    P(H|E) = P(E|H) * 0.5 / (P(E|H)*0.5 + P(E|~H)*0.5)
           = likelihood * 0.5 / 0.5
           = likelihood

    With equal priors, the posterior equals the likelihood regardless of its
    absolute value. This is mathematically exact, not an approximation.
    The formula holds as long as P(E|~H) = 1 - P(E|H), i.e., the likelihood
    ratio model is symmetric - which is the assumption the CALIBRATE phase uses.
    """
    # Guard against numerical edge cases from upstream
    return max(0.0, min(1.0, float(likelihood)))


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def run_independent_replication(record: ProvenanceRecord) -> IndependentReplicationResult:
    """Run convergent independent replication on a ProvenanceRecord.

    Read-only: the record and session state are never modified.
    Deterministic: calling twice with the same record yields identical output.

    Returns IndependentReplicationResult with:
      original_routing   - derived from record.calibration posteriors
      independent_routing - derived from the same likelihoods with flat prior
      agreement_type     - CONVERGENT when both route to the same bucket,
                           DIVERGENT when they differ
      human_review_required - True when DIVERGENT
      prior_sensitivity  - |original_min_posterior - independent_min_posterior|
    """
    calibrations = record.calibration

    if not calibrations:
        return IndependentReplicationResult(
            session_id=record.session_id,
            provenance_record_id=record.record_id,
            original_routing="ACT",
            independent_routing="ACT",
            original_min_posterior=1.0,
            independent_min_posterior=1.0,
            prior_sensitivity=0.0,
            agreement_type="CONVERGENT",
            diverged=False,
            human_review_required=False,
            claims_compared=0,
            notes="No calibration results in record - vacuously CONVERGENT.",
            created_at=record.timestamp,  # F13C3: deterministic
        )

    # Original routing: minimum posterior over HIGH-consequence claims (F13);
    # falls back to all claims when none are tagged HIGH.
    orig_min = _min_high_consequence_posterior(calibrations)
    assert orig_min is not None  # guarded above
    orig_routing = _routing_from_posterior(orig_min)

    # Independent routing: re-derive from flat prior using the same consequence filter.
    flat_calibrations = [
        c.model_copy(update={"posterior": _flat_posterior(c.likelihood)})
        for c in calibrations
    ]
    indep_min = _min_high_consequence_posterior(flat_calibrations)
    assert indep_min is not None
    indep_routing = _routing_from_posterior(indep_min)

    diverged = orig_routing != indep_routing
    agreement_type: str = "DIVERGENT" if diverged else "CONVERGENT"

    notes_parts: list[str] = []
    if diverged:
        notes_parts.append(
            f"Prior-dependent conclusion: original routing {orig_routing!r} "
            f"(posterior_min={orig_min:.3f}) vs. independent routing "
            f"{indep_routing!r} (flat_posterior_min={indep_min:.3f}). "
            "The routing is sensitive to the empirical prior accumulated in "
            "this session. Human review required."
        )
    else:
        notes_parts.append(
            f"Both derivations route to {orig_routing!r}. "
            f"original_min={orig_min:.3f}, independent_min={indep_min:.3f}."
        )

    # F13C3: use record.timestamp so two calls with the same record produce
    # bitwise-identical results (determinism requirement). datetime.utcnow()
    # would differ by wall-clock time on every call.
    return IndependentReplicationResult(
        session_id=record.session_id,
        provenance_record_id=record.record_id,
        original_routing=orig_routing,
        independent_routing=indep_routing,
        original_min_posterior=orig_min,
        independent_min_posterior=indep_min,
        prior_sensitivity=abs(orig_min - indep_min),
        agreement_type=agreement_type,
        diverged=diverged,
        human_review_required=diverged,
        claims_compared=len(calibrations),
        notes=" ".join(notes_parts),
        created_at=record.timestamp,
    )

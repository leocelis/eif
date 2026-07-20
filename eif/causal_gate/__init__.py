"""EIF Phase 2.5 - CAUSAL GATE: check causal reasoning validity.

v4 adds the Causal Evidence Probe (CEP): when a HIGH-consequence claim is
classified at INTERVENTION or COUNTERFACTUAL level, CEP searches for
independent causal evidence (RCTs, meta-analyses) and returns a
structured CausalEvidenceResult with posterior adjustment.
"""

from eif.causal_gate.confound import check_confounders
from eif.causal_gate.direction import check_direction
from eif.causal_gate.evidence_probe import run_causal_evidence_probe, should_probe
from eif.causal_gate.intervention import check_intervention, classify_causal_level
from eif.causal_gate.verdict import (
    apply_verdict_to_posterior,
    posterior_delta,
    provenance_flag_for,
)

__all__ = [
    # v3 (unchanged)
    "check_direction",
    "check_confounders",
    "classify_causal_level",
    "check_intervention",
    # v4 CEP
    "run_causal_evidence_probe",
    "should_probe",
    "apply_verdict_to_posterior",
    "posterior_delta",
    "provenance_flag_for",
]

"""EIF HYPOTHESIS_AGENDA phase - Bayesian priority ranking before FALSIFY.

Closes S3 gap: EIF now proactively selects which assumption to test first,
maximizing Expected Information Gain under resource constraints.

Usage:
    from eif.hypothesis_agenda import build_agenda
    agenda = build_agenda(registry, calibration_map, max_probes=3)
"""

from eif.hypothesis_agenda.agenda import build_agenda
from eif.hypothesis_agenda.scorer import (
    compute_boundary_factor,
    compute_consequence_weight,
    compute_priority_score,
    compute_residual_eig,
    compute_uncertainty_factor,
)

__all__ = [
    "build_agenda",
    "compute_boundary_factor",
    "compute_consequence_weight",
    "compute_priority_score",
    "compute_residual_eig",
    "compute_uncertainty_factor",
]

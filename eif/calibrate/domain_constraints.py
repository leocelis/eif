"""Domain-specific posterior ceiling table - Physics-Informed Metacognition (F1C3).

Implements the Physics-Informed Metacognition principle from
OpenReview LF4RSTZUtA (2025): embedding domain constraints into the
metacognitive process yields a 37.2% ECE reduction vs unconstrained models.

IMPORTANT - Sourcing methodology
─────────────────────────────────
The ceiling values below are CONSERVATIVE REGULATORY PROXIES, not literal
threshold numbers quoted from the standards cited. Regulatory frameworks
constrain acceptable failure rates and require independent validation before
deployment; these ceilings translate that principle into a Bayesian posterior
bound:

  "An AI claim in a high-stakes regulated domain cannot express high
   confidence from parametric evidence alone - independent validation
   evidence is required before reaching high posterior."

The approach is grounded in Physics-Informed Metacognition (Roy et al. 2025):
domain constraints embedded as hard architectural limits outperform
post-hoc confidence calibration by anchoring the posterior to what is
epistemically achievable in each domain.

A future DomainConstraintTable v2 should source literal performance
thresholds from regulatory guidance (e.g., FDA SaMD sensitivity/specificity
requirements, ISO 26262 ASIL D residual risk targets) and map them to
probability bounds via ROC-AUC or equivalent - see OI2 resolution in
eif_v2_intent.yaml.

Research:
  Roy, M. et al. (2025). Physics-Informed Metacognition: Improving LLMs
  Self-Knowledge via Physical Constraints. OpenReview LF4RSTZUtA.
  Findings: 37.2% ECE reduction from domain-constraint embedding.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainConstraintEntry:
    """A single domain's posterior ceiling with regulatory provenance."""

    domain: str
    ceiling: float
    source: str
    note: str


# ─────────────────────────────────────────────────────────────────────────────
# Domain entries - one per constrained domain
#
# ceiling: maximum posterior an AI claim may reach using parametric (P4)
#          evidence alone, before independent validation evidence is present.
# source:  regulatory framework informing the ceiling value.
# note:    rationale connecting the regulatory standard to the ceiling choice.
# ─────────────────────────────────────────────────────────────────────────────

_DOMAIN_ENTRIES: list[DomainConstraintEntry] = [
    DomainConstraintEntry(
        domain="healthcare",
        ceiling=0.95,
        source=(
            "FDA. Artificial Intelligence/Machine Learning (AI/ML)-Based "
            "Software as a Medical Device (SaMD) Action Plan. Jan 2021. "
            "https://www.fda.gov/media/145022/download - "
            "FDA Clinical Decision Support guidance (2022) classifies "
            "high-risk clinical AI as requiring premarket review."
        ),
        note=(
            "Independent clinical validation is mandatory before an AI/ML SaMD "
            "reaches 'substantial evidence' standard. Ceiling 0.95 encodes: "
            "parametric AI evidence alone cannot satisfy FDA's clinical "
            "validation requirement. Any claim with posterior > 0.95 from P4 "
            "alone implies unfounded confidence in a regulated context."
        ),
    ),
    DomainConstraintEntry(
        domain="medical",
        ceiling=0.95,
        source=(
            "FDA AI/ML-Based SaMD Action Plan (Jan 2021) - alias for 'healthcare'."
        ),
        note="Alias for 'healthcare'; same regulatory basis and ceiling apply.",
    ),
    DomainConstraintEntry(
        domain="engineering",
        ceiling=0.92,
        source=(
            "ISO 26262-1:2018 Road Vehicle Functional Safety, §5 (ASIL determination); "
            "ISO 26262-5:2018 Part 5 §8 (hardware target values for ASIL D: "
            "probabilistic metric for random hardware failures PMHF < 1E-8/hr). "
            "IEC 61508:2010 (Functional Safety of E/E/PE Systems) SIL 4: "
            "residual risk < 1E-4 per hour demand rate."
        ),
        note=(
            "ASIL D (highest automotive safety integrity level) and SIL 4 both "
            "require test-validated evidence at every development stage. "
            "Ceiling 0.92 encodes: safety-critical engineering claims require "
            "independent test validation before high posterior is warranted. "
            "The gap from 0.92 to 1.0 is reserved for claims backed by "
            "physical test results (P1/P2 evidence tiers)."
        ),
    ),
    DomainConstraintEntry(
        domain="aviation",
        ceiling=0.90,
        source=(
            "RTCA DO-178C (2011): Software Considerations in Airborne Systems and "
            "Equipment Certification, §6.3 (Independence) and §11.4 "
            "(Software Level A criteria - catastrophic failure condition). "
            "FAA AC 20-115D (2017): Airborne Software Assurance."
        ),
        note=(
            "DO-178C Level A requires independence at every development lifecycle "
            "activity (planning, development, verification). No single-source "
            "claim can achieve full confidence by design. Ceiling 0.90 encodes: "
            "multi-source, independently verified evidence is required before "
            "any aviation safety claim approaches certainty."
        ),
    ),
    DomainConstraintEntry(
        domain="nuclear",
        ceiling=0.90,
        source=(
            "IEC 61513:2011: Nuclear Power Plants - Instrumentation and Control "
            "Important to Safety - General Requirements for Systems, Clause 8 "
            "(Safety I&C system requirements). "
            "IAEA Safety Standards Series SSG-39 (2016): Design of Instrumentation "
            "and Control Systems for Nuclear Power Plants."
        ),
        note=(
            "IEC 61513 Category A qualification requires diverse and redundant "
            "channels with independent verification at each stage. Conservative "
            "treatment mirrors the nuclear safety instrumentation requirement "
            "that no single channel or source constitutes sufficient evidence. "
            "Ceiling 0.90 is shared with aviation - both reflect the highest "
            "available safety integrity category in their respective standards."
        ),
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Public interfaces
# ─────────────────────────────────────────────────────────────────────────────

DOMAIN_CONSTRAINT_TABLE: dict[str, DomainConstraintEntry] = {
    e.domain.lower(): e for e in _DOMAIN_ENTRIES
}

# Flat ceiling lookup - backward-compatible with ece.py DOMAIN_POSTERIOR_CEILINGS
DOMAIN_POSTERIOR_CEILINGS: dict[str, float] = {
    e.domain: e.ceiling for e in _DOMAIN_ENTRIES
}


def get_domain_ceiling(domain: str) -> DomainConstraintEntry | None:
    """Return the DomainConstraintEntry for a domain, or None if unconstrained.

    Case-insensitive. Returns None for domains not in the constraint table
    (no ceiling applies - general-purpose reasoning domain).
    """
    return DOMAIN_CONSTRAINT_TABLE.get(domain.lower())


def list_constrained_domains() -> list[str]:
    """Return all domain names that have a posterior ceiling defined."""
    return list(DOMAIN_CONSTRAINT_TABLE.keys())

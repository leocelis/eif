"""Classify Pearl causal level and detect intervention requirements."""

from __future__ import annotations

from eif.schemas import CausalLevel

_COUNTERFACTUAL_MARKERS = {"would have", "counterfactual", "if x had", "had not", "would not have"}
_INTERVENTION_MARKERS = {"do(", "causes", "interventions", "intervention", "randomized", "rct", "assign"}


def classify_causal_level(hypothesis: str) -> CausalLevel:
    """Classify hypothesis at Pearl's Ladder of Causation.

    Level 3 COUNTERFACTUAL: "would have", "counterfactual", structural model language
    Level 2 INTERVENTION: "do(", "causes", "interventions", RCT language
    Level 1 ASSOCIATION: everything else (correlation, observational)
    """
    h_lower = hypothesis.lower()

    for marker in _COUNTERFACTUAL_MARKERS:
        if marker in h_lower:
            return "COUNTERFACTUAL"

    for marker in _INTERVENTION_MARKERS:
        if marker in h_lower:
            return "INTERVENTION"

    return "ASSOCIATION"


def check_intervention(
    hypothesis: str,
    causal_level: CausalLevel,
    evidence_level: CausalLevel = "ASSOCIATION",
) -> tuple[bool, bool]:
    """Check if the hypothesis requires do-calculus but evidence is only observational.

    Returns:
        (intervention_required, disjunctive_bias_flag)

    intervention_required: True when causal_level > evidence_level
    disjunctive_bias_flag: True when "and" in hypothesis and evidence is ASSOCIATION
        - LLMs systematically treat conjunctive causes as disjunctive (arXiv:2505.09614)
    """
    level_order = {"ASSOCIATION": 0, "INTERVENTION": 1, "COUNTERFACTUAL": 2}

    intervention_required = level_order[causal_level] > level_order[evidence_level]

    h_lower = hypothesis.lower()
    disjunctive_bias_flag = (
        " and " in h_lower
        and evidence_level == "ASSOCIATION"
    )

    return intervention_required, disjunctive_bias_flag

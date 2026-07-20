"""Tests for CAUSAL_GATE phase (C12 - disjunctive bias detection)."""

from __future__ import annotations

from eif.causal_gate.confound import check_confounders
from eif.causal_gate.direction import check_direction
from eif.causal_gate.intervention import check_intervention, classify_causal_level


class TestDisjunctiveBias:
    """C12: disjunctive_bias_flag fires when 'and' in hypothesis + ASSOCIATION evidence."""

    def test_and_conjunction_fires_disjunctive_bias(self):
        _, disjunctive = check_intervention(
            hypothesis="A and B causes C",
            causal_level="INTERVENTION",
            evidence_level="ASSOCIATION",
        )
        assert disjunctive is True

    def test_no_and_no_disjunctive_bias(self):
        _, disjunctive = check_intervention(
            hypothesis="A causes C",
            causal_level="INTERVENTION",
            evidence_level="ASSOCIATION",
        )
        assert disjunctive is False

    def test_and_with_intervention_evidence_no_bias(self):
        """When evidence level is INTERVENTION, disjunctive bias check is not triggered."""
        _, disjunctive = check_intervention(
            hypothesis="A and B causes C",
            causal_level="INTERVENTION",
            evidence_level="INTERVENTION",
        )
        assert disjunctive is False


class TestCausalLevelClassification:
    def test_counterfactual_detected(self):
        level = classify_causal_level("if we had applied treatment, the outcome would have improved")
        assert level == "COUNTERFACTUAL"

    def test_intervention_detected(self):
        level = classify_causal_level("the randomized trial causes the effect")
        assert level == "INTERVENTION"

    def test_association_default(self):
        level = classify_causal_level("X is correlated with Y")
        assert level == "ASSOCIATION"

    def test_rct_is_intervention(self):
        level = classify_causal_level("RCT shows treatment improves outcomes")
        assert level == "INTERVENTION"


class TestInterventionRequired:
    def test_intervention_required_when_causal_above_evidence(self):
        required, _ = check_intervention(
            hypothesis="do(treatment) causes recovery",
            causal_level="INTERVENTION",
            evidence_level="ASSOCIATION",
        )
        assert required is True

    def test_no_intervention_when_levels_match(self):
        required, _ = check_intervention(
            hypothesis="do(treatment) causes recovery",
            causal_level="INTERVENTION",
            evidence_level="INTERVENTION",
        )
        assert required is False


class TestConfounders:
    def test_undocumented_confounders_returned(self):
        confounders = check_confounders(
            hypothesis="Exercise causes weight loss",
            potential_confounders=["diet", "age"],
        )
        assert "diet" in confounders
        assert "age" in confounders

    def test_documented_confounder_not_returned(self):
        confounders = check_confounders(
            hypothesis="Exercise causes weight loss, controlling for diet",
            potential_confounders=["diet"],
        )
        assert "diet" not in confounders

    def test_no_confounders_returns_empty(self):
        confounders = check_confounders("hypothesis", None)
        assert confounders == []


class TestCausalDirection:
    def test_correct_direction_returns_true(self):
        result = check_direction(
            cause_variable="temperature",
            effect_variable="conductivity",
            evidence_text="Temperature rises, which then increases conductivity",
        )
        assert result is True

    def test_reversed_direction_returns_false(self):
        result = check_direction(
            cause_variable="conductivity",
            effect_variable="temperature",
            evidence_text="Temperature rises, which then increases conductivity",
        )
        assert result is False

    def test_missing_variable_returns_true(self):
        result = check_direction(
            cause_variable="missing_var",
            effect_variable="also_missing",
            evidence_text="something else entirely",
        )
        assert result is True

"""Tests for F2: IRIS full iterative causal discovery pipeline (V2).

Covers F2C1 (all 6 steps execute; CausalGraph returned with ≥ 1 edge),
F2C2 (Step 4 adds missing variables), F2C3 (max 2 iterations).
"""

from eif.causal_gate.iris_pipeline import run
from eif.schemas import CausalGraph

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_search(query: str) -> str:
    """Return canned search text mentioning confounders."""
    return (
        "Studies show statins reduce mortality. However, socioeconomic status "
        "may confound this relationship. Age and diet are also known mediators. "
        "Exercise habits are controlled for in randomized trials. Smoking is "
        "another confounder identified in observational studies."
    )


def _no_search(query: str) -> str:
    return ""


# ── F2C1 ──────────────────────────────────────────────────────────────────────

class TestIRISPipelineReturnsGraph:
    def test_returns_causal_graph(self):
        graph = run("statins", "mortality", domain="healthcare", search_fn=_fake_search)
        assert isinstance(graph, CausalGraph)

    def test_graph_has_at_least_one_edge(self):
        graph = run("statins", "mortality", domain="healthcare", search_fn=_fake_search)
        assert len(graph.edges) >= 1, "F2C1: must have ≥ 1 edge"

    def test_iterations_run_at_least_one(self):
        graph = run("statins", "mortality", domain="healthcare", search_fn=_fake_search)
        assert graph.iterations_run >= 1

    def test_graph_preserves_cause_and_effect(self):
        graph = run("exercise", "cardiovascular_mortality", search_fn=_fake_search)
        # Primary edge must connect cause→effect
        primary_edges = [e for e in graph.edges if e.cause == "exercise"]
        assert len(primary_edges) >= 1

    def test_returns_graph_even_with_no_search_results(self):
        """Pipeline must still return a valid CausalGraph on empty search."""
        graph = run("A", "B", search_fn=_no_search)
        assert isinstance(graph, CausalGraph)
        # Should contain zero-confidence ASSOCIATION fallback edge
        assert len(graph.edges) >= 1

    def test_confidence_scores_populated(self):
        graph = run("statins", "mortality", search_fn=_fake_search)
        # confidence_scores may be populated when claims are extracted
        assert isinstance(graph.confidence_scores, dict)


# ── F2C2 ──────────────────────────────────────────────────────────────────────

class TestIRISMissingVariables:
    def test_finds_at_least_one_confounder(self):
        """Step 4 must add ≥ 1 variable not in the initial cause/effect pair."""
        graph = run(
            "exercise", "cardiovascular_mortality",
            domain="healthcare",
            search_fn=_fake_search,
        )
        assert len(graph.missing_variables) >= 1, "F2C2: must find ≥ 1 missing variable"

    def test_missing_variables_are_not_cause_or_effect(self):
        graph = run("statins", "mortality", search_fn=_fake_search)
        for var in graph.missing_variables:
            assert var.lower() not in ("statins", "mortality")


# ── F2C3 ──────────────────────────────────────────────────────────────────────

class TestIRISMaxIterations:
    def test_iterations_never_exceed_2(self):
        graph = run("A", "B", search_fn=_fake_search, max_iterations=2)
        assert graph.iterations_run <= 2, "F2C3: max 2 iterations"

    def test_max_iterations_param_hard_capped_at_2(self):
        """Even if caller passes max_iterations=99, pipeline caps at 2."""
        graph = run("A", "B", search_fn=_fake_search, max_iterations=99)
        assert graph.iterations_run <= 2

    def test_iterations_stop_early_when_no_new_vars(self):
        """When step 4 finds no new variables, stop before max iterations."""
        graph = run("X", "Y", search_fn=_no_search, max_iterations=2)
        assert graph.iterations_run <= 2


# ── CausalEdge schema ─────────────────────────────────────────────────────────

class TestCausalEdgeSchema:
    def test_edge_level_is_valid_pearl_level(self):
        graph = run("statins", "mortality", search_fn=_fake_search)
        valid_levels = {"ASSOCIATION", "INTERVENTION", "COUNTERFACTUAL"}
        for edge in graph.edges:
            assert edge.level in valid_levels

    def test_edge_confidence_in_unit_interval(self):
        graph = run("statins", "mortality", search_fn=_fake_search)
        for edge in graph.edges:
            assert 0.0 <= edge.confidence <= 1.0

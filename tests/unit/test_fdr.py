"""Tests for FDR correction annotation in HYPOTHESIS_AGENDA.

Research: Benjamini & Hochberg (1995); frontier_debates.md §6 - multiple
comparisons under hypothesis search; standard corrections annotate rather
than filter when test set is search-generated.
"""

from __future__ import annotations

from eif.hypothesis_agenda.fdr import _FDR_HIGH_N, _FDR_MED_N, apply_fdr_correction


class TestFDRCorrection:
    """apply_fdr_correction computes BH thresholds and surfaces warnings."""

    def test_low_n_no_warning(self) -> None:
        adjustments, warning = apply_fdr_correction(total_claims=3)
        assert warning is None
        assert all(a.inflation_risk == "LOW" for a in adjustments)

    def test_medium_n_note_emitted(self) -> None:
        adjustments, warning = apply_fdr_correction(total_claims=_FDR_MED_N + 1)
        assert warning is not None
        assert "MEDIUM" in warning or "moderate" in warning.lower()
        assert all(a.inflation_risk == "MEDIUM" for a in adjustments)

    def test_high_n_warning_emitted(self) -> None:
        adjustments, warning = apply_fdr_correction(total_claims=_FDR_HIGH_N + 1)
        assert warning is not None
        assert "FDR WARNING" in warning
        assert all(a.inflation_risk == "HIGH" for a in adjustments)

    def test_bh_formula_rank_1(self) -> None:
        """α_adjusted(k=1) = (1/N) × α."""
        adjustments, _ = apply_fdr_correction(total_claims=10, alpha=0.05)
        assert abs(adjustments[0].alpha_adjusted - (1 / 10 * 0.05)) < 1e-8

    def test_bh_formula_rank_n(self) -> None:
        """α_adjusted(k=N) = α (last rank equals nominal α)."""
        adjustments, _ = apply_fdr_correction(total_claims=5, alpha=0.05)
        assert abs(adjustments[-1].alpha_adjusted - 0.05) < 1e-8

    def test_adjustment_count_equals_n(self) -> None:
        for n in [1, 5, 10, 20]:
            adjustments, _ = apply_fdr_correction(total_claims=n)
            assert len(adjustments) == n

    def test_ranks_are_sequential(self) -> None:
        adjustments, _ = apply_fdr_correction(total_claims=6)
        assert [a.rank for a in adjustments] == list(range(1, 7))

    def test_high_n_warning_mentions_count(self) -> None:
        n = 15
        _, warning = apply_fdr_correction(total_claims=n)
        assert str(n) in warning


class TestFDRWiredIntoAgenda:
    """HypothesisAgenda includes fdr_warning and fdr_alpha_adjusted fields."""

    def _make_agenda(self, n_claims: int):
        from eif.hypothesis_agenda import build_agenda
        from eif.schemas import ClaimInput

        claims = [
            ClaimInput(
                text=f"claim {i}",
                claim_type="ASSUMED",
                consequence_of_wrong="HIGH",
            )
            for i in range(n_claims)
        ]
        from eif.declare.registry import build_registry
        registry, _ = build_registry("test-sess", "test decision", claims)
        return build_agenda(registry)

    def test_low_n_fdr_warning_none(self) -> None:
        agenda = self._make_agenda(3)
        assert agenda.fdr_warning is None

    def test_high_n_fdr_warning_set(self) -> None:
        agenda = self._make_agenda(_FDR_HIGH_N + 2)
        assert agenda.fdr_warning is not None
        assert "FDR" in agenda.fdr_warning

    def test_items_have_fdr_fields(self) -> None:
        agenda = self._make_agenda(3)
        for item in agenda.items:
            assert item.fdr_alpha_adjusted is not None
            assert item.fdr_inflation_risk is not None

    def test_fdr_does_not_change_ranking(self) -> None:
        """FDR annotates only - items[0] is the same claim before/after."""
        agenda = self._make_agenda(8)
        top_text = agenda.items[0].claim_text
        # Rebuild - should be stable
        agenda2 = self._make_agenda(8)
        assert agenda2.items[0].claim_text == top_text

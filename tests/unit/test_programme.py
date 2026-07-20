"""Tests for PROGRAMME phase (C11 - Lakatos programme health)."""

from __future__ import annotations

from eif.programme.monitor import compute_status
from eif.programme.status import derive_status_text
from eif.schemas import ProgrammeSignals


class TestProgrammeStatus:
    """C11: PROGRESSIVE/STABLE/DEGENERATIVE logic from Lakatos criteria."""

    def test_progressive_status(self):
        signals = ProgrammeSignals(
            novel_prediction_rate=0.5,
            confirmed_prediction_rate=0.4,
            patch_rate=0.1,
            oscillation_count=0,
        )
        assert compute_status(signals) == "PROGRESSIVE"

    def test_degenerative_high_patch_rate(self):
        signals = ProgrammeSignals(
            novel_prediction_rate=0.5,
            confirmed_prediction_rate=0.4,
            patch_rate=0.7,
            oscillation_count=0,
        )
        assert compute_status(signals) == "DEGENERATIVE"

    def test_degenerative_high_oscillation(self):
        signals = ProgrammeSignals(
            novel_prediction_rate=0.5,
            confirmed_prediction_rate=0.4,
            patch_rate=0.1,
            oscillation_count=3,
        )
        assert compute_status(signals) == "DEGENERATIVE"

    def test_degenerative_no_confirmed_predictions(self):
        signals = ProgrammeSignals(
            novel_prediction_rate=0.5,
            confirmed_prediction_rate=0.05,
            patch_rate=0.1,
            oscillation_count=0,
        )
        assert compute_status(signals) == "DEGENERATIVE"

    def test_stable_default(self):
        signals = ProgrammeSignals()
        assert compute_status(signals) == "DEGENERATIVE"

    def test_stable_moderate_performance(self):
        signals = ProgrammeSignals(
            novel_prediction_rate=0.2,
            confirmed_prediction_rate=0.15,
            patch_rate=0.2,
            oscillation_count=1,
        )
        assert compute_status(signals) == "STABLE"

    def test_boundary_progressive_threshold(self):
        signals = ProgrammeSignals(
            novel_prediction_rate=0.31,
            confirmed_prediction_rate=0.31,
            patch_rate=0.39,
            oscillation_count=1,
        )
        assert compute_status(signals) == "PROGRESSIVE"

    def test_degenerative_patch_rate_exact_boundary(self):
        """patch_rate=0.6 is the inclusive boundary: must return DEGENERATIVE (C11)."""
        signals = ProgrammeSignals(
            novel_prediction_rate=0.5,
            confirmed_prediction_rate=0.4,
            patch_rate=0.6,
            oscillation_count=0,
        )
        assert compute_status(signals) == "DEGENERATIVE"


class TestDeriveStatusText:
    def test_progressive_has_continue_recommendation(self):
        signals = ProgrammeSignals(
            novel_prediction_rate=0.5,
            confirmed_prediction_rate=0.4,
            patch_rate=0.1,
        )
        _, recommendation = derive_status_text("PROGRESSIVE", signals)
        assert "Continue" in recommendation or "continue" in recommendation.lower()

    def test_degenerative_has_declare_recommendation(self):
        signals = ProgrammeSignals(patch_rate=0.8)
        _, recommendation = derive_status_text("DEGENERATIVE", signals)
        assert "DECLARE" in recommendation

    def test_stable_has_prediction_recommendation(self):
        signals = ProgrammeSignals(
            novel_prediction_rate=0.2,
            confirmed_prediction_rate=0.15,
        )
        _, recommendation = derive_status_text("STABLE", signals)
        assert "prediction" in recommendation.lower() or "PROGRESSIVE" in recommendation

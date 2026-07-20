"""Tests for FALSIFY phase (C3 - SPRT POPPER orientation)."""

from __future__ import annotations

from eif.falsify.sprt import run_sprt
from eif.falsify.trivial_check import is_trivial
from eif.schemas import FalsificationCondition


def _make_fc(**overrides) -> FalsificationCondition:
    defaults = dict(
        claim_text="API returns JSON",
        condition="Response is not JSON",
        threshold="Any failure falsifies",
        test_procedure="Inspect Content-Type",
        sprt_alpha=0.05,
        sprt_beta=0.10,
        sprt_effect_size=0.2,
    )
    defaults.update(overrides)
    return FalsificationCondition(**defaults)


class TestSPRTPopper:
    """C3: POPPER orientation - all-False observations must reach REJECT."""

    def test_all_false_rejects(self):
        """All observations refuting the claim must trigger REJECT."""
        fc = _make_fc()
        observations = [False] * 50
        result = run_sprt(fc, observations)
        assert result.decision == "REJECT"

    def test_all_true_accepts(self):
        """All observations supporting the claim must trigger ACCEPT."""
        fc = _make_fc()
        observations = [True] * 50
        result = run_sprt(fc, observations)
        assert result.decision == "ACCEPT"

    def test_mixed_continues(self):
        """Balanced observations should remain CONTINUE (insufficient evidence)."""
        fc = _make_fc()
        observations = [True, False] * 5  # 10 observations, balanced
        result = run_sprt(fc, observations)
        assert result.decision == "CONTINUE"

    def test_boundaries_correct(self):
        """accept_boundary = beta/(1-alpha); reject_boundary = (1-beta)/alpha."""
        fc = _make_fc(sprt_alpha=0.05, sprt_beta=0.10)
        result = run_sprt(fc, [])  # no observations → CONTINUE
        expected_accept = 0.10 / (1 - 0.05)
        expected_reject = (1 - 0.10) / 0.05
        assert abs(result.accept_boundary - expected_accept) < 1e-6
        assert abs(result.reject_boundary - expected_reject) < 1e-6

    def test_empty_observations_continue(self):
        fc = _make_fc()
        result = run_sprt(fc, [])
        assert result.decision == "CONTINUE"
        assert result.observations_count == 0

    def test_stopped_early_flag(self):
        fc = _make_fc()
        stopped = run_sprt(fc, [False] * 50)
        not_stopped = run_sprt(fc, [True, False] * 2)
        assert stopped.stopped_early is True
        assert not_stopped.stopped_early is False


class TestTrivialCheck:
    def test_trivial_condition_always(self):
        assert is_trivial("this always passes", "some threshold") is True

    def test_trivial_threshold_any(self):
        assert is_trivial("condition text", "any") is True

    def test_trivial_empty_threshold(self):
        assert is_trivial("condition text", "") is True

    def test_non_trivial(self):
        assert is_trivial(
            "Response Content-Type != application/json",
            "Any single failure"
        ) is False

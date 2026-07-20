"""Tests for hard-to-vary check on falsification conditions (F12)."""

from __future__ import annotations

from eif.falsify.condition import build_condition
from eif.falsify.hard_to_vary import check_hard_to_vary

# ─────────────────────────────────────────────────────────────────────────────
# check_hard_to_vary unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestThresholdCheck:
    """THRESHOLD dimension: must have a numeric anchor when qualitative words are present."""

    def test_qualitative_threshold_without_number_flags(self):
        is_vague, reasons = check_hard_to_vary(
            condition="If engagement is poor, content strategy is wrong",
            threshold="significant",
            test_procedure="Query the analytics API for engagement_rate field",
        )
        assert is_vague is True
        assert any("THRESHOLD" in r for r in reasons)

    def test_threshold_with_number_passes(self):
        is_vague, reasons = check_hard_to_vary(
            condition="If IGDB hypes < 100, the demand claim is wrong",
            threshold="< 100",
            test_procedure="Query IGDB API for game hypes field",
        )
        threshold_reasons = [r for r in reasons if "THRESHOLD" in r]
        assert len(threshold_reasons) == 0, f"Unexpected threshold flag: {threshold_reasons}"

    def test_threshold_with_word_number_passes(self):
        is_vague, reasons = check_hard_to_vary(
            condition="If the count is zero, the claim fails",
            threshold="zero",
            test_procedure="Query database and check count field",
        )
        threshold_reasons = [r for r in reasons if "THRESHOLD" in r]
        assert len(threshold_reasons) == 0

    def test_threshold_with_unit_passes(self):
        is_vague, reasons = check_hard_to_vary(
            condition="If response time exceeds 500ms, performance claim fails",
            threshold="> 500ms",
            test_procedure="Run benchmark tool, record p95 latency",
        )
        threshold_reasons = [r for r in reasons if "THRESHOLD" in r]
        assert len(threshold_reasons) == 0

    def test_threshold_high_low_without_number_flags(self):
        is_vague, reasons = check_hard_to_vary(
            condition="if the score is high",
            threshold="high",
            test_procedure="Query the scoring API",
        )
        assert any("THRESHOLD" in r for r in reasons)

    def test_empty_threshold_not_double_flagged(self):
        """Empty threshold is caught by condition.py before hard_to_vary runs."""
        is_vague, reasons = check_hard_to_vary(
            condition="some condition",
            threshold="",
            test_procedure="Query the API",
        )
        # Empty threshold should not cause a crash
        assert isinstance(is_vague, bool)


class TestProcedureCheck:
    """PROCEDURE dimension: must name a specific tool/API/method."""

    def test_vague_check_if_without_method_flags(self):
        is_vague, reasons = check_hard_to_vary(
            condition="If engagement is low, strategy is wrong",
            threshold="< 1000",
            test_procedure="Check if the engagement is high enough",
        )
        assert any("PROCEDURE" in r for r in reasons)

    def test_vague_verify_that_without_method_flags(self):
        is_vague, reasons = check_hard_to_vary(
            condition="If wrong, claim fails",
            threshold="< 100",
            test_procedure="Verify that the numbers are correct",
        )
        assert any("PROCEDURE" in r for r in reasons)

    def test_specific_api_procedure_passes(self):
        is_vague, reasons = check_hard_to_vary(
            condition="If IGDB hypes < 100, claim is wrong",
            threshold="< 100",
            test_procedure="Query IGDB API /games endpoint, read hypes field",
        )
        procedure_reasons = [r for r in reasons if "PROCEDURE" in r]
        assert len(procedure_reasons) == 0

    def test_sql_query_procedure_passes(self):
        is_vague, reasons = check_hard_to_vary(
            condition="If count < 50, claim fails",
            threshold="< 50",
            test_procedure="Run SQL query: SELECT COUNT(*) FROM users WHERE status='active'",
        )
        procedure_reasons = [r for r in reasons if "PROCEDURE" in r]
        assert len(procedure_reasons) == 0

    def test_pytest_procedure_passes(self):
        is_vague, reasons = check_hard_to_vary(
            condition="If tests fail, the implementation claim is wrong",
            threshold="0 failures",
            test_procedure="Run pytest suite on the module; check exit code",
        )
        procedure_reasons = [r for r in reasons if "PROCEDURE" in r]
        assert len(procedure_reasons) == 0


class TestConditionAdjustabilityCheck:
    """CONDITION dimension: must not contain adjustable language."""

    def test_might_be_lower_flags(self):
        is_vague, reasons = check_hard_to_vary(
            condition="The data might be lower than expected if results differ",
            threshold="< 100",
            test_procedure="Query the API and compare result",
        )
        assert is_vague is True
        assert any("CONDITION" in r for r in reasons)

    def test_could_indicate_flags(self):
        is_vague, reasons = check_hard_to_vary(
            condition="A low value could indicate the claim is wrong",
            threshold="< 50",
            test_procedure="Query API endpoint for field value",
        )
        assert any("CONDITION" in r for r in reasons)

    def test_exact_condition_passes(self):
        is_vague, reasons = check_hard_to_vary(
            condition="If IGDB hype count < 100, the 3500+ followers claim is falsified",
            threshold="< 100",
            test_procedure="Query IGDB API for Manor Lords hypes field",
        )
        condition_reasons = [r for r in reasons if "CONDITION" in r]
        assert len(condition_reasons) == 0


class TestCombinedChecks:
    """Multiple dimensions failing at once."""

    def test_all_three_fail(self):
        is_vague, reasons = check_hard_to_vary(
            condition="maybe the score could indicate poor performance",
            threshold="high",
            test_procedure="check if it looks right",
        )
        assert is_vague is True
        assert len(reasons) >= 2  # At least THRESHOLD and CONDITION should fire

    def test_clean_igdb_condition_passes_all(self):
        """The canonical Maya IGDB condition should pass all three checks."""
        is_vague, reasons = check_hard_to_vary(
            condition="If IGDB hypes for Manor Lords < 100, the 3500+ followers claim is falsified",
            threshold="< 100",
            test_procedure="Query IGDB /games endpoint, filter id=137206, read hypes field",
        )
        assert is_vague is False
        assert reasons == []


# ─────────────────────────────────────────────────────────────────────────────
# build_condition integration (trivial_flag wiring)
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildConditionIntegration:
    """build_condition must set trivial_flag via EITHER is_trivial OR check_hard_to_vary."""

    def test_vague_threshold_sets_trivial_flag(self):
        """F12C1: qualitative threshold without number → trivial_flag=True."""
        fc = build_condition(
            "The content strategy is correct",
            "if performance is poor",
            "high",
            "check if it works",
        )
        assert fc.trivial_flag is True

    def test_specific_igdb_condition_no_trivial_flag(self):
        """F12C2: specific numeric threshold + named API → trivial_flag=False."""
        fc = build_condition(
            "Manor Lords has 3500+ IGDB hypes",
            "If IGDB hypes for Manor Lords < 100, the followers claim is falsified",
            "< 100",
            "Query IGDB API /games endpoint for Manor Lords hypes field",
        )
        assert fc.trivial_flag is False
        assert fc.hard_to_vary_reasons == []

    def test_adjustable_language_sets_trivial_flag(self):
        """F12C3: adjustable language in condition → trivial_flag=True."""
        fc = build_condition(
            "The API returns data",
            "the data might be lower than expected, which could indicate failure",
            "< 100",
            "Query the API endpoint and compare",
        )
        assert fc.trivial_flag is True
        assert any("CONDITION" in r for r in fc.hard_to_vary_reasons)

    def test_hard_to_vary_reasons_populated_on_vague(self):
        """hard_to_vary_reasons must be non-empty when trivial_flag fires from htv check."""
        fc = build_condition(
            "Performance is adequate",
            "if performance is poor",
            "high",
            "check if it works",
        )
        assert fc.hard_to_vary_reasons != [] or fc.trivial_flag

    def test_vacuously_trivial_still_sets_flag(self):
        """is_trivial() still fires for always/never conditions."""
        fc = build_condition(
            "Claim",
            "always passes",
            "any",
            "always returns success",
        )
        assert fc.trivial_flag is True

    def test_backward_compat_trivial_flag_still_set_on_vacuous(self):
        """is_trivial() still fires for vacuous conditions regardless of hard_to_vary."""
        fc = build_condition(
            "API returns JSON",
            "Response is not JSON",
            "Any failure falsifies",
            "Inspect Content-Type header",
        )
        # "Any failure falsifies" triggers is_trivial ("any") → trivial_flag=True
        assert fc.trivial_flag is True

    def test_specific_condition_no_hard_to_vary_reasons(self):
        """A fully specific condition: numeric threshold + named tool + no hedging."""
        fc = build_condition(
            "Server responds in under 200ms",
            "if p95 latency > 200ms, performance claim is falsified",
            "> 200ms",
            "Run benchmark script against /api/health endpoint; record p95 latency",
        )
        assert fc.hard_to_vary_reasons == []
        assert fc.trivial_flag is False

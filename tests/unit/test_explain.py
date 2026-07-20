"""Tests for EXPLAIN phase (C7 - hard-to-vary verdict)."""

from __future__ import annotations

import pytest

from eif.explain.artifact import build_artifact
from eif.explain.hard_to_vary import check_hard_to_vary
from eif.explain.reach import classify_reach
from eif.schemas import ExplanationDetail


class TestHardToVary:
    """C7: Generic or empty prediction_impact must produce FAIL verdict."""

    def test_empty_details_fails(self):
        assert check_hard_to_vary([]) == "FAIL"

    def test_empty_impact_fails(self):
        details = [ExplanationDetail(detail_text="uses jsonify()", prediction_impact="")]
        assert check_hard_to_vary(details) == "FAIL"

    def test_generic_phrase_fails(self):
        details = [
            ExplanationDetail(
                detail_text="uses jsonify()",
                prediction_impact="changes the explanation",
            )
        ]
        assert check_hard_to_vary(details) == "FAIL"

    def test_paraphrase_fails(self):
        """Impact that is essentially a restatement of the detail should FAIL."""
        # Jaccard: intersection=4 ("the","function","processes","request")
        #          union=5 → overlap = 4/5 = 0.80 > 0.70 → FAIL
        details = [
            ExplanationDetail(
                detail_text="the function processes the request",
                prediction_impact="the function processes the request quickly",
            )
        ]
        assert check_hard_to_vary(details) == "FAIL"

    def test_load_bearing_impact_passes(self):
        details = [
            ExplanationDetail(
                detail_text="uses jsonify()",
                prediction_impact="Remove jsonify() → Content-Type becomes text/html",
            )
        ]
        assert check_hard_to_vary(details) == "PASS"

    def test_multiple_good_details_passes(self):
        details = [
            ExplanationDetail(
                detail_text="Flask route",
                prediction_impact="Changing to FastAPI would require different serializer",
            ),
            ExplanationDetail(
                detail_text="jsonify()",
                prediction_impact="Remove it and response loses application/json header",
            ),
        ]
        assert check_hard_to_vary(details) == "PASS"

    def test_one_bad_detail_among_good_fails(self):
        details = [
            ExplanationDetail(
                detail_text="Flask route",
                prediction_impact="Changing to FastAPI would require different serializer",
            ),
            ExplanationDetail(
                detail_text="jsonify()",
                prediction_impact="matters",  # generic
            ),
        ]
        assert check_hard_to_vary(details) == "FAIL"


class TestBuildArtifact:
    def test_empty_new_explanation_raises(self):
        with pytest.raises(ValueError, match="new_explanation cannot be empty"):
            build_artifact(
                prior_explanation="old",
                new_explanation="",
                details=[],
                testable_predictions=["some prediction"],
            )

    def test_no_predictions_raises(self):
        with pytest.raises(ValueError, match="testable_prediction"):
            build_artifact(
                prior_explanation="old",
                new_explanation="new explanation here",
                details=[],
                testable_predictions=[],
            )

    def test_valid_artifact_built(self):
        artifact, _ = build_artifact(
            prior_explanation="Flask defaults",
            new_explanation="Flask uses jsonify() which sets Content-Type",
            details=[
                {"detail_text": "jsonify()", "prediction_impact": "Remove it → Content-Type changes"},
            ],
            testable_predictions=["Remove jsonify() → Content-Type changes"],
        )
        assert artifact.new_explanation != ""
        assert len(artifact.testable_predictions) == 1


class TestReach:
    def test_local_by_default(self):
        reach = classify_reach("this specific function returns JSON")
        assert reach in ("LOCAL", "BROADER")

    def test_returns_valid_scope(self):
        reach = classify_reach("all API endpoints in this system return JSON")
        assert reach in ("LOCAL", "BROADER")

"""Tests for F4: Research Object + DeepTRACE 8-dimension audit (V2).

Covers F4C1 (all 8 dimensions populated, overall_score = mean, flags for < 0.5),
F4C2 (evidence older than 180 days flagged as STALE_EVIDENCE).
"""

from datetime import datetime, timedelta

from eif.record.research_object import build_research_object
from eif.schemas import (
    AssumptionRegistry,
    CalibrationResult,
    Claim,
    DeepTRACEAudit,
    ProvenanceRecord,
    ResearchObject,
)


def _make_registry(session_id: str = "s1", n_known: int = 2) -> AssumptionRegistry:
    claims = [
        Claim(
            text=f"claim {i}",
            claim_type="KNOWN",
            evidence_source=f"https://example.com/{i}",
        )
        for i in range(n_known)
    ]
    return AssumptionRegistry(session_id=session_id, decision="test decision", known=claims)


def _make_record(
    session_id: str = "s1",
    registry: AssumptionRegistry | None = None,
    stale_days_ago: int | None = None,
) -> ProvenanceRecord:
    if registry is None:
        registry = _make_registry(session_id)

    if stale_days_ago is not None:
        # Add a claim with a retrieval date older than stale_days_ago
        old_date = datetime.utcnow() - timedelta(days=stale_days_ago)
        stale_claim = Claim(
            text="stale evidence claim",
            claim_type="ASSUMED",
            retrieved_at=old_date,
        )
        registry = registry.model_copy(update={"assumed": [stale_claim]})

    return ProvenanceRecord(
        session_id=session_id,
        decision="test decision",
        registry=registry,
        calibration=[
            CalibrationResult(
                claim_text="c1", prior=0.5, likelihood=0.7, posterior=0.8,
                confidence_tier="HIGH", prior_strategy="max_entropy",
            )
        ],
        tools_invoked=["eif_declare", "eif_calibrate"],
        models_used=["gpt-4"],
        input_fingerprint="abc123",
        model_config_snapshot={"eif_engine": "2.0.0"},
    )


# ── F4C1: All 8 dimensions populated ─────────────────────────────────────────

class TestAllDimensionsPopulated:
    def test_returns_research_object(self):
        record = _make_record()
        obj = build_research_object(record)
        assert isinstance(obj, ResearchObject)

    def test_all_8_dimensions_not_none(self):
        record = _make_record()
        obj = build_research_object(record)
        dims = obj.dimensions
        assert dims.answer_accuracy is not None
        assert dims.source_accuracy is not None
        assert dims.citation_accuracy is not None
        assert dims.claim_evidence_alignment is not None
        assert dims.reasoning_transparency is not None
        assert dims.uncertainty_disclosure is not None
        assert dims.coverage_completeness is not None
        assert dims.temporal_currency is not None

    def test_overall_score_is_mean_of_8(self):
        record = _make_record()
        obj = build_research_object(record)
        dims = obj.dimensions
        expected = round(sum([
            dims.answer_accuracy, dims.source_accuracy, dims.citation_accuracy,
            dims.claim_evidence_alignment, dims.reasoning_transparency,
            dims.uncertainty_disclosure, dims.coverage_completeness, dims.temporal_currency,
        ]) / 8, 4)
        assert abs(obj.dimensions.overall_score - expected) < 1e-6

    def test_flags_generated_for_low_dimensions(self):
        """A session without challenge or causal evidence should have coverage_completeness < 0.5."""
        record = _make_record()
        obj = build_research_object(record)
        # coverage_completeness is low when no contrary_evidence_considered
        assert any("DIMENSION_LOW" in flag for flag in obj.provenance_flags)

    def test_session_id_propagated(self):
        record = _make_record(session_id="abc-123")
        obj = build_research_object(record)
        assert obj.session_id == "abc-123"

    def test_models_used_propagated(self):
        record = _make_record()
        obj = build_research_object(record)
        assert "gpt-4" in obj.models_used

    def test_overall_score_in_unit_interval(self):
        record = _make_record()
        obj = build_research_object(record)
        assert 0.0 <= obj.dimensions.overall_score <= 1.0


# ── F4C2: STALE evidence flagged ──────────────────────────────────────────────

class TestStaleEvidence:
    def test_stale_flag_added_for_old_evidence(self):
        record = _make_record(stale_days_ago=200)
        obj = build_research_object(record, stale_days=180)
        stale_flags = [f for f in obj.provenance_flags if "STALE_EVIDENCE" in f]
        assert len(stale_flags) >= 1, "F4C2: must flag evidence older than 180 days"

    def test_temporal_currency_below_1_when_stale(self):
        record = _make_record(stale_days_ago=200)
        obj = build_research_object(record, stale_days=180)
        assert obj.dimensions.temporal_currency < 1.0

    def test_no_stale_flag_for_fresh_evidence(self):
        from datetime import datetime
        registry = _make_registry()
        fresh_claim = Claim(
            text="fresh claim",
            claim_type="ASSUMED",
            retrieved_at=datetime.utcnow() - timedelta(days=5),
        )
        registry = registry.model_copy(update={"assumed": [fresh_claim]})
        record = _make_record(registry=registry)
        obj = build_research_object(record, stale_days=180)
        stale_flags = [f for f in obj.provenance_flags if "STALE_EVIDENCE" in f]
        assert len(stale_flags) == 0

    def test_stale_sources_list_populated(self):
        record = _make_record(stale_days_ago=200)
        obj = build_research_object(record, stale_days=180)
        assert len(obj.stale_sources) >= 1


# ── DeepTRACEAudit model ──────────────────────────────────────────────────────

class TestDeepTRACEAuditModel:
    def test_dim_scores_returns_all_8_keys(self):
        audit = DeepTRACEAudit(
            answer_accuracy=0.9, source_accuracy=0.8, citation_accuracy=0.7,
            claim_evidence_alignment=0.6, reasoning_transparency=0.5,
            uncertainty_disclosure=0.4, coverage_completeness=0.3, temporal_currency=0.2,
        )
        keys = set(audit.dim_scores.keys())
        expected = {
            "answer_accuracy", "source_accuracy", "citation_accuracy",
            "claim_evidence_alignment", "reasoning_transparency",
            "uncertainty_disclosure", "coverage_completeness", "temporal_currency",
        }
        assert keys == expected

    def test_overall_score_computes_correctly(self):
        vals = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]
        audit = DeepTRACEAudit(
            answer_accuracy=vals[0], source_accuracy=vals[1],
            citation_accuracy=vals[2], claim_evidence_alignment=vals[3],
            reasoning_transparency=vals[4], uncertainty_disclosure=vals[5],
            coverage_completeness=vals[6], temporal_currency=vals[7],
        )
        expected = round(sum(vals) / 8, 4)
        assert abs(audit.overall_score - expected) < 1e-6

"""Tests for empirical catch rate measurement (F14)."""

from __future__ import annotations

import pytest

from eif.cost_model.catch_rate_empirical import (
    EMPIRICAL_MIN_SESSIONS,
    compute_session_catch_rates,
    get_catch_rate_report,
    load_catch_rate_store,
    update_catch_rate_store,
)
from eif.schemas import (
    AssumptionRegistry,
    CalibrationResult,
    CatchRateReport,
    ChallengeResult,
    Claim,
    FalsificationCondition,
    OutcomeRecord,
    ProvenanceRecord,
    SPRTResult,
    UpdateResult,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("EIF_STORE_DIR", str(tmp_path))
    return tmp_path


def _make_registry(session_id: str = "s1") -> AssumptionRegistry:
    return AssumptionRegistry(
        session_id=session_id,
        decision="Test decision",
        assumed=[Claim(text="Claim A", claim_type="ASSUMED", consequence_of_wrong="HIGH")],
        guessed=[Claim(text="Claim B", claim_type="GUESSED", consequence_of_wrong="HIGH")],
        known=[],
    )


def _make_record(
    session_id: str = "s1",
    record_id: str = "r1",
    has_sprt_reject: bool = False,
    has_trivial: bool = False,
    counter_evidence: bool = False,
    has_challenge: bool = False,
    prior_posterior: float = 0.5,
    updated_posterior: float = 0.5,
    has_update: bool = False,
) -> ProvenanceRecord:
    registry = _make_registry(session_id)

    fc = FalsificationCondition(
        claim_text="Claim A",
        condition="if < 100, wrong",
        threshold="< 100",
        test_procedure="Query API",
        trivial_flag=has_trivial,
    )
    sprt = SPRTResult(
        decision="REJECT" if has_sprt_reject else "ACCEPT",
        likelihood_ratio=18.0 if has_sprt_reject else 0.1,
        observations_count=20,
        alpha=0.05,
        beta=0.10,
        accept_boundary=0.105,
        reject_boundary=18.0,
    )
    challenge = None
    if has_challenge:
        challenge = ChallengeResult(
            claim_text="Claim A",
            counter_evidence_found=counter_evidence,
            verdict="SURVIVES" if not counter_evidence else "DEFEATED",
        )
    updates = []
    if has_update:
        updates = [UpdateResult(
            hypothesis="Claim A",
            prior_posterior=prior_posterior,
            new_evidence="some evidence",
            updated_posterior=updated_posterior,
            eig=0.05,
            recommendation="MAINTAIN_COURSE",
        )]
    cal = CalibrationResult(
        claim_text="Claim A",
        prior=0.5,
        likelihood=0.5,
        posterior=0.5,
        confidence_tier="MEDIUM",
        prior_strategy="max_entropy",
    )

    record = ProvenanceRecord(
        session_id=session_id,
        decision="Test",
        registry=registry,
        falsification_conditions=[fc],
        sprt_results=[sprt],
        challenge=challenge,
        updates=updates,
        calibration=[cal],
    )
    # Override record_id using object mutation (Pydantic v2 allows it on non-frozen models)
    object.__setattr__(record, "record_id", record_id)
    return record


def _make_outcome(session_id: str, record_id: str, outcome: bool) -> OutcomeRecord:
    return OutcomeRecord(
        session_id=session_id,
        provenance_record_id=record_id,
        outcome=outcome,
    )


# ─────────────────────────────────────────────────────────────────────────────
# compute_session_catch_rates
# ─────────────────────────────────────────────────────────────────────────────

class TestFEmpirical:

    def test_f_empirical_half_when_one_of_two_caught(self):
        """F14C1: 1 caught out of 2 wrong sessions → f_empirical=0.5."""
        records = [
            _make_record("s1", "r1", has_sprt_reject=True),   # caught
            _make_record("s2", "r2", has_sprt_reject=False),  # missed
        ]
        outcomes = [
            _make_outcome("s1", "r1", outcome=False),  # wrong
            _make_outcome("s2", "r2", outcome=False),  # wrong
        ]
        report = compute_session_catch_rates(records, outcomes)
        assert report.f_empirical == pytest.approx(0.5, abs=0.01)

    def test_f_empirical_zero_when_nothing_caught(self):
        records = [_make_record("s1", "r1", has_sprt_reject=False)]
        outcomes = [_make_outcome("s1", "r1", outcome=False)]
        report = compute_session_catch_rates(records, outcomes)
        assert report.f_empirical == pytest.approx(0.0)

    def test_f_empirical_one_when_all_caught(self):
        records = [
            _make_record("s1", "r1", has_sprt_reject=True),
            _make_record("s2", "r2", has_trivial=True),
        ]
        outcomes = [
            _make_outcome("s1", "r1", outcome=False),
            _make_outcome("s2", "r2", outcome=False),
        ]
        report = compute_session_catch_rates(records, outcomes)
        assert report.f_empirical == pytest.approx(1.0)

    def test_f_empirical_zero_when_no_labeled_wrong(self):
        """F14C1: no wrong-labeled records → f_empirical=0.0 (intent: 'Returns 0.0 when denominator is 0')."""
        records = [_make_record("s1", "r1", has_sprt_reject=True)]
        outcomes = [_make_outcome("s1", "r1", outcome=True)]  # correct, not wrong
        report = compute_session_catch_rates(records, outcomes)
        assert report.f_empirical == pytest.approx(0.0)

    def test_unlabeled_records_excluded_from_denominator(self):
        """Records without outcome labels are excluded from f denominator."""
        records = [
            _make_record("s1", "r1", has_sprt_reject=True),
            _make_record("s2", "r2", has_sprt_reject=False),  # no label
        ]
        outcomes = [_make_outcome("s1", "r1", outcome=False)]  # only s1 labeled
        report = compute_session_catch_rates(records, outcomes)
        # Only 1 labeled-wrong record and it was caught
        assert report.f_empirical == pytest.approx(1.0)


class TestCEmpirical:

    def test_c_empirical_one_when_all_challenge_finds_evidence(self):
        records = [
            _make_record("s1", "r1", has_challenge=True, counter_evidence=True),
            _make_record("s2", "r2", has_challenge=True, counter_evidence=True),
        ]
        report = compute_session_catch_rates(records, [])
        assert report.c_empirical == pytest.approx(1.0)

    def test_c_empirical_zero_when_no_counter_evidence(self):
        records = [
            _make_record("s1", "r1", has_challenge=True, counter_evidence=False),
        ]
        report = compute_session_catch_rates(records, [])
        assert report.c_empirical == pytest.approx(0.0)

    def test_c_empirical_none_when_no_challenge_ran(self):
        records = [_make_record("s1", "r1", has_challenge=False)]
        report = compute_session_catch_rates(records, [])
        assert report.c_empirical is None


class TestUEmpirical:

    def test_u_empirical_one_when_routing_changes_across_threshold(self):
        """UPDATE changes posterior from REVISE to HALT → u_empirical=1.0."""
        records = [_make_record(
            "s1", "r1",
            has_update=True,
            prior_posterior=0.50,   # REVISE bucket
            updated_posterior=0.10, # HALT bucket
        )]
        report = compute_session_catch_rates(records, [])
        assert report.u_empirical == pytest.approx(1.0)

    def test_u_empirical_zero_when_no_routing_change(self):
        records = [_make_record(
            "s1", "r1",
            has_update=True,
            prior_posterior=0.50,
            updated_posterior=0.60,  # still REVISE
        )]
        report = compute_session_catch_rates(records, [])
        assert report.u_empirical == pytest.approx(0.0)

    def test_u_empirical_none_when_no_updates(self):
        records = [_make_record("s1", "r1", has_update=False)]
        report = compute_session_catch_rates(records, [])
        assert report.u_empirical is None


class TestDataStatus:

    def test_insufficient_data_below_threshold(self):
        """F14C2: < 3 labeled sessions → INSUFFICIENT_DATA."""
        records = [_make_record("s1", "r1")]
        outcomes = [_make_outcome("s1", "r1", outcome=False)]
        report = compute_session_catch_rates(records, outcomes)
        assert report.data_status == "INSUFFICIENT_DATA"
        assert report.f_used == pytest.approx(0.6)  # literature default

    def test_sufficient_at_min_sessions(self, monkeypatch):
        """F14C3: >= EMPIRICAL_MIN_SESSIONS → SUFFICIENT; empirical rates used."""
        n = EMPIRICAL_MIN_SESSIONS
        records = [
            _make_record(f"s{i}", f"r{i}", has_sprt_reject=True)
            for i in range(n)
        ]
        outcomes = [_make_outcome(f"s{i}", f"r{i}", outcome=False) for i in range(n)]
        report = compute_session_catch_rates(records, outcomes)
        assert report.data_status == "SUFFICIENT"
        # With all caught, f_used should be 1.0 (empirical)
        assert report.f_used == pytest.approx(1.0)

    def test_compound_error_both_returned_when_sufficient(self):
        """F14C3: both compound_error_empirical and compound_error_literature returned."""
        n = EMPIRICAL_MIN_SESSIONS
        records = [
            _make_record(
                f"s{i}", f"r{i}",
                has_sprt_reject=True,
                has_challenge=True, counter_evidence=True,
                has_update=True, prior_posterior=0.50, updated_posterior=0.10,
            )
            for i in range(n)
        ]
        outcomes = [_make_outcome(f"s{i}", f"r{i}", outcome=False) for i in range(n)]
        report = compute_session_catch_rates(records, outcomes)
        assert report.compound_error_empirical is not None
        assert report.compound_error_literature is not None


# ─────────────────────────────────────────────────────────────────────────────
# Persistent store
# ─────────────────────────────────────────────────────────────────────────────

class TestCatchRateStore:

    def test_get_report_returns_default_when_empty(self, store_dir):
        """F14C2: no store → default with literature values and INSUFFICIENT_DATA."""
        report = get_catch_rate_report()
        assert report.data_status == "INSUFFICIENT_DATA"
        assert report.f_used == pytest.approx(0.6)
        assert report.compound_error_literature is not None

    def test_update_and_load_roundtrip(self, store_dir):
        r = CatchRateReport(
            f_empirical=0.7,
            c_empirical=0.5,
            u_empirical=0.4,
            sessions_measured=10,
            data_status="SUFFICIENT",
            compound_error_literature=0.12,
            compound_error_empirical=0.09,
            f_used=0.7,
            c_used=0.5,
            u_used=0.4,
        )
        update_catch_rate_store(r)
        loaded = load_catch_rate_store()
        assert loaded is not None
        assert loaded.f_empirical == pytest.approx(0.7)
        assert loaded.data_status == "SUFFICIENT"

"""Tests for cross-session outcome store (F11)."""

from __future__ import annotations

import pytest


@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    """Redirect the outcome store to a temp directory for each test."""
    monkeypatch.setenv("EIF_STORE_DIR", str(tmp_path))
    return tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# Basic store operations
# ─────────────────────────────────────────────────────────────────────────────

class TestOutcomeStorePersistence:

    def test_store_empty_when_file_missing(self, store_dir):
        from eif.record.outcome_store import load_outcomes
        assert load_outcomes() == []

    def test_record_outcome_creates_file(self, store_dir):
        from eif.record.outcome_store import load_outcomes, record_outcome
        rec = record_outcome("s1", "r1", outcome=False, domain="gaming")
        assert rec.session_id == "s1"
        assert rec.outcome is False
        assert rec.domain == "gaming"
        store = load_outcomes()
        assert len(store) == 1

    def test_record_outcome_is_append_only(self, store_dir):
        """F11C1: calling record_outcome twice produces 2 entries, never overwrites."""
        from eif.record.outcome_store import load_outcomes, record_outcome
        record_outcome("s1", "r1", outcome=False)
        record_outcome("s1", "r1", outcome=False)  # same ids - still append
        store = load_outcomes()
        assert len(store) == 2

    def test_record_outcome_multiple_sessions(self, store_dir):
        from eif.record.outcome_store import load_outcomes, record_outcome
        for i in range(5):
            record_outcome(f"s{i}", f"r{i}", outcome=(i % 2 == 0))
        store = load_outcomes()
        assert len(store) == 5


class TestEmpiricalPrior:

    def test_prior_returns_half_when_insufficient(self, store_dir):
        """F11C2: fewer than PRIOR_EMPIRICAL_MIN records → prior = 0.5."""
        from eif.record.outcome_store import compute_empirical_prior, record_outcome
        # Add only 5 records (< 10 threshold)
        for i in range(5):
            record_outcome(f"s{i}", f"r{i}", outcome=True, domain="gaming")
        assert compute_empirical_prior("gaming") == pytest.approx(0.5)

    def test_prior_is_mean_accuracy_at_threshold(self, store_dir):
        """F11C2: >= PRIOR_EMPIRICAL_MIN records → prior = mean(outcome)."""
        from eif.record.outcome_store import compute_empirical_prior, record_outcome
        # 8 correct out of 12
        for i in range(8):
            record_outcome(f"s_t{i}", f"r_t{i}", outcome=True, domain="gaming")
        for i in range(4):
            record_outcome(f"s_f{i}", f"r_f{i}", outcome=False, domain="gaming")
        prior = compute_empirical_prior("gaming")
        assert prior == pytest.approx(8 / 12, abs=1e-6)

    def test_prior_domain_filtered(self, store_dir):
        """Domain filter is applied correctly; other domains not included."""
        from eif.record.outcome_store import compute_empirical_prior, record_outcome
        for i in range(10):
            record_outcome(f"g{i}", f"g{i}", outcome=True, domain="gaming")
        for i in range(10):
            record_outcome(f"h{i}", f"h{i}", outcome=False, domain="healthcare")
        gaming_prior = compute_empirical_prior("gaming")
        health_prior = compute_empirical_prior("healthcare")
        assert gaming_prior == pytest.approx(1.0)
        assert health_prior == pytest.approx(0.0)

    def test_prior_no_domain_uses_all_records(self, store_dir):
        from eif.record.outcome_store import compute_empirical_prior, record_outcome
        for i in range(10):
            record_outcome(f"s{i}", f"r{i}", outcome=(i < 7), domain=None)
        prior = compute_empirical_prior(None)
        assert prior == pytest.approx(0.7)


class TestECEState:

    def test_ece_state_uncalibrated_below_threshold(self, store_dir):
        """F11C3: < 30 sessions → UNCALIBRATED (intent: seed 25 → to_grounded=5)."""
        from eif.record.outcome_store import get_ece_state, get_sessions_to_grounded, record_outcome
        for i in range(25):
            record_outcome(f"s{i}", f"r{i}", outcome=True)
        assert get_ece_state() == "UNCALIBRATED"
        assert get_sessions_to_grounded() == 5

    def test_ece_state_grounded_at_threshold(self, store_dir):
        """F11C3: >= 30 sessions → LABEL_GROUNDED (intent: seed 35 → sessions_to_grounded=0)."""
        from eif.record.outcome_store import get_ece_state, get_sessions_to_grounded, record_outcome
        for i in range(35):
            record_outcome(f"s{i}", f"r{i}", outcome=True)
        assert get_ece_state() == "LABEL_GROUNDED"
        assert get_sessions_to_grounded() == 0

    def test_sessions_to_grounded_decrements(self, store_dir):
        from eif.record.outcome_store import get_sessions_to_grounded, record_outcome
        for i in range(10):
            record_outcome(f"s{i}", f"r{i}", outcome=True)
        assert get_sessions_to_grounded() == 20


class TestStorageRobustness:

    def test_corrupted_file_returns_empty(self, store_dir):
        from eif.record.outcome_store import load_outcomes
        store_file = store_dir / "outcome_store.json"
        store_file.write_text("{not valid json}", encoding="utf-8")
        result = load_outcomes()
        assert result == []

    def test_records_have_required_fields(self, store_dir):
        from eif.record.outcome_store import record_outcome
        rec = record_outcome("sess", "prov_rec", outcome=True, domain="test")
        assert rec.record_id is not None
        assert rec.recorded_at is not None
        assert rec.session_id == "sess"
        assert rec.provenance_record_id == "prov_rec"

"""Tests for PIEVO paradigm revision detection (eif.update.paradigm)."""

from __future__ import annotations

from eif.schemas import UpdateResult
from eif.update.paradigm import (
    PARADIGM_ALERT_THRESHOLD,
    PARADIGM_MIN_AVG_SHIFT,
    check_paradigm_revision,
)


def _make_update(prior: float, posterior: float) -> UpdateResult:
    return UpdateResult(
        hypothesis="test hypothesis",
        prior_posterior=prior,
        new_evidence="test evidence",
        updated_posterior=posterior,
        eig=abs(posterior - prior),
        recommendation="MAINTAIN_COURSE",
    )


class TestParadigmRevisionCheck:
    """PIEVO: Detect systematic unidirectional posterior drift."""

    def test_returns_none_when_too_few_updates(self):
        updates = [_make_update(0.5, 0.4)] * (PARADIGM_ALERT_THRESHOLD - 1)
        assert check_paradigm_revision(updates) is None

    def test_returns_none_when_drift_mixed(self):
        updates = [
            _make_update(0.5, 0.4),   # DOWN
            _make_update(0.4, 0.5),   # UP
            _make_update(0.5, 0.4),   # DOWN
        ]
        assert check_paradigm_revision(updates) is None

    def test_fires_on_consistent_downward_drift(self):
        updates = [
            _make_update(0.5, 0.45),
            _make_update(0.45, 0.40),
            _make_update(0.40, 0.35),
        ]
        alert = check_paradigm_revision(updates, session_id="sess-001")
        assert alert is not None
        assert alert.direction == "DOWN"
        assert alert.consecutive_updates == PARADIGM_ALERT_THRESHOLD
        assert alert.avg_posterior_shift >= PARADIGM_MIN_AVG_SHIFT

    def test_fires_on_consistent_upward_drift(self):
        updates = [
            _make_update(0.3, 0.35),
            _make_update(0.35, 0.40),
            _make_update(0.40, 0.45),
        ]
        alert = check_paradigm_revision(updates, session_id="sess-002")
        assert alert is not None
        assert alert.direction == "UP"

    def test_does_not_fire_when_shift_too_small(self):
        updates = [
            _make_update(0.5000, 0.5005),
            _make_update(0.5005, 0.5010),
            _make_update(0.5010, 0.5015),
        ]
        assert check_paradigm_revision(updates) is None

    def test_uses_only_most_recent_threshold_updates(self):
        """Early mixed updates should not suppress an alert from the last 3."""
        early = [_make_update(0.5, 0.6)] * 5  # UP
        recent = [
            _make_update(0.6, 0.55),   # DOWN
            _make_update(0.55, 0.50),  # DOWN
            _make_update(0.50, 0.45),  # DOWN
        ]
        alert = check_paradigm_revision(early + recent, session_id="sess-003")
        assert alert is not None
        assert alert.direction == "DOWN"

    def test_alert_session_id_propagated(self):
        updates = [_make_update(0.5, 0.45)] * PARADIGM_ALERT_THRESHOLD
        alert = check_paradigm_revision(updates, session_id="my-session")
        assert alert is not None
        assert alert.session_id == "my-session"

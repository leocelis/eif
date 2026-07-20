"""Tests for exploratory/confirmatory claim labeling (schemas.py + registry.py).

Research: Lakens (2021) Perspectives on Psychological Science 16(3), 639-648 - 
inferential conclusions from exploratory analysis contaminate confirmatory
inference; explicit labeling required.
"""

from __future__ import annotations

import pytest

from eif.declare.registry import build_registry
from eif.schemas import ClaimInput, ClaimMode


def _make_claim(text: str, claim_type: str = "ASSUMED", mode: ClaimMode = "UNSPECIFIED") -> ClaimInput:
    return ClaimInput(text=text, claim_type=claim_type, claim_mode=mode)


class TestClaimModeSchema:
    """claim_mode field exists and validates correctly."""

    def test_default_mode_is_unspecified(self) -> None:
        c = ClaimInput(text="test claim", claim_type="ASSUMED")
        assert c.claim_mode == "UNSPECIFIED"

    def test_exploratory_mode_accepted(self) -> None:
        c = ClaimInput(text="test", claim_type="ASSUMED", claim_mode="EXPLORATORY")
        assert c.claim_mode == "EXPLORATORY"

    def test_confirmatory_mode_accepted(self) -> None:
        c = ClaimInput(text="test", claim_type="ASSUMED", claim_mode="CONFIRMATORY")
        assert c.claim_mode == "CONFIRMATORY"

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError):
            ClaimInput(text="test", claim_type="ASSUMED", claim_mode="INVENTED")  # type: ignore[arg-type]


class TestExplorationOnlyWarning:
    """registry.py emits EXPLORATION_ONLY warning when all claims are EXPLORATORY."""

    def test_exploration_only_warning_emitted(self) -> None:
        claims = [
            _make_claim("claim A", mode="EXPLORATORY"),
            _make_claim("claim B", mode="EXPLORATORY"),
        ]
        _, warnings = build_registry("sess-001", "test decision", claims)
        exploration_warnings = [w for w in warnings if w.startswith("EXPLORATION_ONLY:")]
        assert len(exploration_warnings) == 1

    def test_mixed_modes_no_warning(self) -> None:
        claims = [
            _make_claim("claim A", mode="EXPLORATORY"),
            _make_claim("claim B", mode="CONFIRMATORY"),
        ]
        _, warnings = build_registry("sess-002", "test decision", claims)
        exploration_warnings = [w for w in warnings if w.startswith("EXPLORATION_ONLY:")]
        assert len(exploration_warnings) == 0

    def test_unspecified_mode_no_warning(self) -> None:
        claims = [
            _make_claim("claim A", mode="UNSPECIFIED"),
            _make_claim("claim B", mode="UNSPECIFIED"),
        ]
        _, warnings = build_registry("sess-003", "test decision", claims)
        exploration_warnings = [w for w in warnings if w.startswith("EXPLORATION_ONLY:")]
        assert len(exploration_warnings) == 0

    def test_single_exploratory_claim_warns(self) -> None:
        claims = [_make_claim("only claim", mode="EXPLORATORY")]
        _, warnings = build_registry("sess-004", "test decision", claims)
        exploration_warnings = [w for w in warnings if w.startswith("EXPLORATION_ONLY:")]
        assert len(exploration_warnings) == 1

    def test_claim_mode_propagated_to_registry_claim(self) -> None:
        claims = [_make_claim("a claim", mode="CONFIRMATORY")]
        registry, _ = build_registry("sess-005", "decision", claims)
        all_claims = list(registry.known) + list(registry.assumed) + list(registry.guessed)
        assert all_claims[0].claim_mode == "CONFIRMATORY"


# ── F9C2: CONFIRMATORY claim without falsification_condition → HARKING risk ──

class TestConfirmatoryHarkingFlag:
    """F9C2: CONFIRMATORY claims require a falsification_condition (Lakens 2021).

    A CONFIRMATORY claim without a pre-registered falsification condition is a
    HARKING risk: there is no verifiable evidence the hypothesis was stated
    before results were known.
    """

    def test_confirmatory_without_condition_sets_harking_flag(self) -> None:
        """F9C2: CONFIRMATORY + no falsification_condition → harking_flag == True."""
        from eif.declare.harking_guard import detect_harking
        from eif.schemas import ClaimInput

        claims = [
            ClaimInput(
                text="Manor Lords demand is high based on IGDB hypes",
                claim_type="ASSUMED",
                claim_mode="CONFIRMATORY",
                # no falsification_condition - this is a HARKING risk
            )
        ]
        registry, _ = build_registry("sess-f9c2", "Commission article series", claims)
        flagged_registry = detect_harking(registry)

        assert flagged_registry.harking_flag is True

    def test_confirmatory_with_condition_no_harking_flag(self) -> None:
        """F9C2: CONFIRMATORY + falsification_condition set → no HARKING flag."""
        from eif.declare.harking_guard import detect_harking
        from eif.schemas import ClaimInput

        claims = [
            ClaimInput(
                text="Manor Lords demand is high based on IGDB hypes",
                claim_type="ASSUMED",
                claim_mode="CONFIRMATORY",
                falsification_condition="IF IGDB hypes < 1000 THEN claim is false",
            )
        ]
        registry, _ = build_registry("sess-f9c2b", "Commission article series", claims)
        flagged_registry = detect_harking(registry)

        assert flagged_registry.harking_flag is False

    def test_exploratory_without_condition_no_harking_flag(self) -> None:
        """Exploratory claims don't require falsification_condition (only CONFIRMATORY do)."""
        from eif.declare.harking_guard import detect_harking
        from eif.schemas import ClaimInput

        claims = [
            ClaimInput(
                text="Exploratory observation about Manor Lords",
                claim_type="ASSUMED",
                claim_mode="EXPLORATORY",
                # no falsification_condition - that's OK for EXPLORATORY
            )
        ]
        registry, _ = build_registry("sess-f9c2c", "Research exploration", claims)
        flagged_registry = detect_harking(registry)

        assert flagged_registry.harking_flag is False

    def test_unspecified_without_condition_no_harking_flag(self) -> None:
        """UNSPECIFIED mode without condition does not fire F9C2 HARKING."""
        from eif.declare.harking_guard import detect_harking
        from eif.schemas import ClaimInput

        claims = [
            ClaimInput(
                text="Some unspecified claim",
                claim_type="GUESSED",
                claim_mode="UNSPECIFIED",
            )
        ]
        registry, _ = build_registry("sess-f9c2d", "Decision", claims)
        flagged_registry = detect_harking(registry)

        assert flagged_registry.harking_flag is False

    def test_both_triggers_can_fire_independently(self) -> None:
        """F9C2 fires independently of the V1 timestamp trigger."""
        from eif.declare.harking_guard import detect_harking
        from eif.schemas import ClaimInput

        claims = [
            ClaimInput(
                text="CONFIRMATORY without condition",
                claim_type="ASSUMED",
                claim_mode="CONFIRMATORY",
            )
        ]
        registry, _ = build_registry("sess-f9c2e", "Decision", claims)
        # No decision_timestamp → V1 trigger won't fire; only F9C2 fires
        flagged_registry = detect_harking(registry, decision_timestamp=None)
        assert flagged_registry.harking_flag is True

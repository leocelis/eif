"""Tests for F8C4/F8C5: DASES adaptive multi-round falsification.

New constraints implemented in the gap fix:
  F8C4: round N+1 targets specifically what round N survived.
  F8C5: max_rounds = 3; claim accepted only if ALL rounds survived.
"""

import json

from eif.challenge.replicator import (
    _DASES_SYSTEM_PROMPT,
    _MAX_ROUNDS,
    run_adversarial_replication,
)
from eif.schemas import ReplicationResult

# ── F8C4: adaptive progression ────────────────────────────────────────────────

class TestAdaptiveProgression:
    def test_round2_test_differs_from_round1(self):
        """Round 2 must target what round 1 survived - not repeat round 1 test."""
        rounds_received = []

        def fake_llm_tracking(prompt, tool_name="", system_prompt=None):
            rounds_received.append(prompt)
            if len(rounds_received) == 1:
                # Round 1: claim survives
                return json.dumps({
                    "test_designed": "Boundary test: verify claim holds when IGDB hype count is under 100 across 20 similar games released in the same quarter.",
                    "test_result": "Claim survived - the author acknowledges IGDB metrics are approximate.",
                    "survived": True,
                    "confidence": 0.6,
                    "defense_mechanism": "Author defended by citing IGDB hypes as an approximate signal, not exact count",
                })
            # Round 2: adaptive targeting the defense mechanism
            return json.dumps({
                "test_designed": "Precision test: if IGDB hypes are acknowledged as approximate, define the acceptable error margin. Test whether a 100x error (36 vs 3500) is within that margin under any interpretation.",
                "test_result": "Claim fails - 100x error exceeds any reasonable approximation margin.",
                "survived": False,
                "confidence": 0.75,
                "defense_mechanism": "",
            })

        result = run_adversarial_replication(
            claim_text="Manor Lords has 3500 IGDB hype followers",
            supporting_evidence=["IGDB shows hypes=36"],
            llm_fn=fake_llm_tracking,
            max_rounds=2,
        )

        # Two LLM calls must have been made
        assert len(rounds_received) == 2
        # Round 2 prompt must reference the defense mechanism from round 1
        assert "defense" in rounds_received[1].lower() or "survived" in rounds_received[1].lower()
        # Final verdict: failed round 2 → not survived
        assert result.survived is False

    def test_stops_early_when_claim_fails_round1(self):
        """If round 1 fails, round 2 should NOT run (no point testing a failed claim)."""
        call_count = {"n": 0}

        def fake_llm_counter(prompt, tool_name="", system_prompt=None):
            call_count["n"] += 1
            return json.dumps({
                "test_designed": "A specific indirect test of the causal chain behind the hype count claim mechanism.",
                "test_result": "Claim fails - IGDB hypes=36, not 3500.",
                "survived": False,
                "confidence": 0.85,
                "defense_mechanism": "",
            })

        result = run_adversarial_replication(
            claim_text="Manor Lords has 3500 IGDB hypes",
            llm_fn=fake_llm_counter,
            max_rounds=3,
        )

        # Should have stopped after round 1 failure
        assert call_count["n"] == 1
        assert result.survived is False

    def test_max_rounds_respected(self):
        """Never runs more than _MAX_ROUNDS rounds regardless of survival."""
        call_count = {"n": 0}

        def always_survives(prompt, tool_name="", system_prompt=None):
            call_count["n"] += 1
            return json.dumps({
                "test_designed": f"Test round {call_count['n']}: specific indirect test targeting hidden assumptions of the stated mechanism.",
                "test_result": "Claim survived this round.",
                "survived": True,
                "confidence": 0.5,
                "defense_mechanism": "claim defended by citing independent corroboration",
            })

        run_adversarial_replication(
            claim_text="A causes B",
            llm_fn=always_survives,
            max_rounds=_MAX_ROUNDS,
        )

        assert call_count["n"] <= _MAX_ROUNDS


# ── F8C5: accept only if all rounds survived ──────────────────────────────────

class TestAcceptOnlyIfAllSurvived:
    def test_survived_false_when_any_round_fails(self):
        round_results = [True, False, True]  # fails round 2
        call_count = {"n": 0}

        def mixed_survival(prompt, tool_name="", system_prompt=None):
            i = call_count["n"]
            call_count["n"] += 1
            survived = round_results[i] if i < len(round_results) else False
            return json.dumps({
                "test_designed": f"Round {i+1}: indirect mechanism test for the claim's causal chain assumptions here.",
                "test_result": f"Round {i+1} result: {'survived' if survived else 'failed'}.",
                "survived": survived,
                "confidence": 0.5,
                "defense_mechanism": "defended via implicit assumption" if survived else "",
            })

        result = run_adversarial_replication(
            claim_text="X causes Y",
            llm_fn=mixed_survival,
            max_rounds=3,
        )

        # Fails at round 2 → stops there, survived=False
        assert result.survived is False

    def test_survived_true_only_when_all_pass(self):
        call_count = {"n": 0}

        def all_survive(prompt, tool_name="", system_prompt=None):
            call_count["n"] += 1
            return json.dumps({
                "test_designed": f"Round {call_count['n']}: targeted indirect falsification test for the specific mechanism.",
                "test_result": "Survived - no failure found.",
                "survived": True,
                "confidence": 0.55,
                "defense_mechanism": "strong independent corroboration from multiple sources",
            })

        result = run_adversarial_replication(
            claim_text="Claim that is hard to break",
            llm_fn=all_survive,
            max_rounds=2,
        )

        assert result.survived is True

    def test_heuristic_multi_round_completes(self):
        """Heuristic path (no LLM) produces a multi-round result without error."""
        result = run_adversarial_replication(
            claim_text="Manor Lords has 3500 IGDB hype followers indicating strong demand",
            max_rounds=_MAX_ROUNDS,
        )
        assert isinstance(result, ReplicationResult)
        assert len(result.test_designed) >= 50
        assert "DASES" in result.replication_mode
        assert isinstance(result.survived, bool)

    def test_multi_round_summary_in_test_result(self):
        """test_result should summarize all rounds."""
        result = run_adversarial_replication(
            claim_text="X causes Y with 100x evidence",
            max_rounds=2,
        )
        assert "Round" in result.test_result or "round" in result.test_result.lower()
        assert "VERDICT" in result.test_result


# ── Backward compatibility: single-round still works ─────────────────────────

class TestBackwardCompatibility:
    def test_max_rounds_1_behaves_like_single_shot(self):
        call_count = {"n": 0}

        def fake_llm(prompt, tool_name="", system_prompt=None):
            call_count["n"] += 1
            return json.dumps({
                "test_designed": "A specific indirect test targeting the hidden mechanism of the claim.",
                "test_result": "Failed - mechanism not independently verifiable.",
                "survived": False,
                "confidence": 0.7,
                "defense_mechanism": "",
            })

        result = run_adversarial_replication(
            claim_text="A causes B",
            llm_fn=fake_llm,
            max_rounds=1,
        )

        assert call_count["n"] == 1
        assert result.survived is False

    def test_existing_heuristic_tests_still_run(self):
        """Heuristic path must still return valid ReplicationResult."""
        result = run_adversarial_replication(claim_text="A causes B")
        assert isinstance(result, ReplicationResult)
        assert "evaluate" not in _DASES_SYSTEM_PROMPT.lower()

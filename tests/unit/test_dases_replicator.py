"""Tests for F8: DASES adversarial replicator (V2).

Covers F8C1 (system prompt constraints), F8C2 (test_designed quality),
F8C3 (replication_result in eif_challenge response when mode='DASES'),
and schema integrity.
"""

from eif.challenge.replicator import (
    _DASES_SYSTEM_PROMPT,
    _enforce_test_quality,
    run_adversarial_replication,
)
from eif.schemas import ReplicationResult

# ── F8C1: System prompt constraints ───────────────────────────────────────────

class TestSystemPromptConstraints:
    def test_evaluate_not_in_system_prompt(self):
        assert "evaluate" not in _DASES_SYSTEM_PROMPT.lower(), "F8C1: 'evaluate' must not appear"

    def test_fail_in_system_prompt(self):
        has_fail = "fail" in _DASES_SYSTEM_PROMPT.lower()
        has_falsif = "falsif" in _DASES_SYSTEM_PROMPT.lower()
        assert has_fail or has_falsif, "F8C1: prompt must contain 'fail' or 'falsif'"


# ── F8C2: test_designed quality ───────────────────────────────────────────────

class TestTestDesignedQuality:
    def test_heuristic_returns_non_empty_test(self):
        result = run_adversarial_replication(claim_text="A causes B")
        assert len(result.test_designed) >= 50, "F8C2: test_designed must be ≥ 50 chars"

    def test_test_designed_not_verbatim_claim(self):
        claim = "A causes B"
        result = run_adversarial_replication(claim_text=claim)
        assert result.test_designed != claim, "F8C2: must not be verbatim restatement"

    def test_test_designed_always_50_chars(self):
        result = run_adversarial_replication(claim_text="X")
        assert len(result.test_designed) >= 50

    def test_test_result_non_empty(self):
        result = run_adversarial_replication(claim_text="Statins reduce mortality")
        assert len(result.test_result) > 0

    def test_enforce_test_quality_pads_short_test(self):
        short = "Too short"
        padded = _enforce_test_quality(short, "some claim")
        assert len(padded) >= 50

    def test_enforce_test_quality_replaces_verbatim_claim(self):
        claim = "A causes B"
        fixed = _enforce_test_quality(claim, claim)
        assert fixed != claim
        assert len(fixed) >= 50


# ── ReplicationResult schema ──────────────────────────────────────────────────

class TestReplicationResultSchema:
    def test_returns_replication_result(self):
        result = run_adversarial_replication(claim_text="Statins reduce mortality")
        assert isinstance(result, ReplicationResult)

    def test_survived_is_bool(self):
        result = run_adversarial_replication(claim_text="A causes B")
        assert isinstance(result.survived, bool)

    def test_confidence_in_unit_interval(self):
        result = run_adversarial_replication(claim_text="A causes B")
        assert 0.0 <= result.confidence <= 1.0

    def test_claim_text_propagated(self):
        result = run_adversarial_replication(claim_text="My special claim")
        assert result.claim_text == "My special claim"

    def test_replication_mode_is_dases(self):
        result = run_adversarial_replication(claim_text="test")
        assert result.replication_mode == "DASES"


# ── LLM integration path (mocked) ────────────────────────────────────────────

class TestLLMPath:
    def test_llm_response_parsed(self):
        def fake_llm(prompt, tool_name="", system_prompt=None):
            return '{"test_designed": "Test whether the claimed effect disappears when we control for selection bias across 3 independent datasets from different time periods.", "test_result": "Effect found robust.", "survived": true, "confidence": 0.7, "defense_mechanism": ""}'

        # max_rounds=1: test single-round LLM parsing behavior
        result = run_adversarial_replication(
            claim_text="A causes B",
            llm_fn=fake_llm,
            max_rounds=1,
        )
        assert result.survived is True
        assert result.confidence == 0.7
        assert len(result.test_designed) >= 50

    def test_bad_llm_json_falls_back_to_heuristic(self):
        def bad_llm(prompt, tool_name="", system_prompt=None):
            return "not valid json"

        result = run_adversarial_replication(claim_text="A causes B", llm_fn=bad_llm, max_rounds=1)
        assert isinstance(result, ReplicationResult)
        assert len(result.test_designed) >= 50

    def test_confidence_clamped_to_unit_interval(self):
        def llm_with_bad_confidence(prompt, tool_name="", system_prompt=None):
            return '{"test_designed": "A very specific indirect test that targets the hidden assumptions of the stated causal mechanism here.", "test_result": "Result text here.", "survived": false, "confidence": 1.5}'

        result = run_adversarial_replication(claim_text="test", llm_fn=llm_with_bad_confidence)
        assert result.confidence <= 1.0

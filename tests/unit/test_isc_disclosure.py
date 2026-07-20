"""Tests for F5: ISC AI Disclosure Taxonomy (V2).

Covers F5C1 (≥ 1 entry per pipeline phase), F5C2 (HALT verdict → human_required entry),
and schema integrity.
"""

from eif.record.isc_disclosure import generate_isc_disclosure
from eif.schemas import (
    AssumptionRegistry,
    CalibrationResult,
    ChallengeResult,
    Claim,
    FalsificationCondition,
    ISCDisclosure,
    ProvenanceRecord,
)


def _make_record(
    session_id: str = "s1",
    with_challenge: bool = False,
    with_falsify: bool = False,
) -> ProvenanceRecord:
    registry = AssumptionRegistry(
        session_id=session_id,
        decision="test decision",
        known=[Claim(text="k1", claim_type="KNOWN", evidence_source="https://x.com")],
    )
    calibration = [
        CalibrationResult(
            claim_text="k1", prior=0.5, likelihood=0.6, posterior=0.7,
            confidence_tier="MEDIUM", prior_strategy="max_entropy",
        )
    ]
    challenge = None
    if with_challenge:
        challenge = ChallengeResult(
            claim_text="k1",
            critic_model="gpt-4",
            critic_independence="DIFFERENT_OBJECTIVE",
            counter_evidence_found=True,
            counter_evidence=["counter 1"],
            verdict="NEEDS_REVISION",
        )
    fc = []
    if with_falsify:
        fc = [FalsificationCondition(
            claim_text="k1",
            condition="if X then falsified",
            threshold="0.05",
            test_procedure="run A/B test",
        )]
    return ProvenanceRecord(
        session_id=session_id,
        decision="test decision",
        registry=registry,
        calibration=calibration,
        challenge=challenge,
        falsification_conditions=fc,
        models_used=["gpt-4"],
        tools_invoked=["eif_declare", "eif_calibrate"],
    )


# ── F5C1: ≥ 1 entry per phase ────────────────────────────────────────────────

class TestAtLeastOneEntryPerPhase:
    def test_returns_isc_disclosure(self):
        record = _make_record()
        disclosure = generate_isc_disclosure(record)
        assert isinstance(disclosure, ISCDisclosure)

    def test_minimum_5_entries_for_full_session(self):
        record = _make_record(with_challenge=True, with_falsify=True)
        disclosure = generate_isc_disclosure(record)
        assert len(disclosure.entries) >= 5, "F5C1: ≥ 5 entries for full session"

    def test_each_entry_has_model_name(self):
        record = _make_record()
        disclosure = generate_isc_disclosure(record)
        for entry in disclosure.entries:
            assert entry.model_name, f"Entry {entry.eif_phase} missing model_name"

    def test_each_entry_has_task_description(self):
        record = _make_record()
        disclosure = generate_isc_disclosure(record)
        for entry in disclosure.entries:
            assert len(entry.task_description) > 10

    def test_isc_draft_compliance_flagged(self):
        record = _make_record()
        disclosure = generate_isc_disclosure(record)
        for entry in disclosure.entries:
            assert entry.isc_draft_compliance is True

    def test_session_id_propagated(self):
        record = _make_record(session_id="sess-xyz")
        disclosure = generate_isc_disclosure(record)
        assert disclosure.session_id == "sess-xyz"

    def test_isc_version_is_draft_2026(self):
        record = _make_record()
        disclosure = generate_isc_disclosure(record)
        assert disclosure.isc_version == "draft-2026"


# ── F5C2: HALT verdict → human_required entry ────────────────────────────────

class TestHALTVerdictHumanRequired:
    def test_halt_adds_human_required_entry(self):
        record = _make_record()
        disclosure = generate_isc_disclosure(record, verdict="HALT")
        human_entries = [e for e in disclosure.entries if e.isc_type == "human_required"]
        assert len(human_entries) >= 1, "F5C2: HALT must produce human_required entry"

    def test_human_required_entry_has_review_step(self):
        record = _make_record()
        disclosure = generate_isc_disclosure(record, verdict="HALT")
        human_entries = [e for e in disclosure.entries if e.isc_type == "human_required"]
        for e in human_entries:
            assert e.human_review_step is not None

    def test_act_verdict_no_human_required(self):
        record = _make_record()
        disclosure = generate_isc_disclosure(record, verdict="ACT")
        human_entries = [e for e in disclosure.entries if e.isc_type == "human_required"]
        assert len(human_entries) == 0

    def test_halt_phase_in_entry(self):
        record = _make_record()
        disclosure = generate_isc_disclosure(record, verdict="HALT")
        phases = [e.eif_phase for e in disclosure.entries]
        assert "HALT_DECISION" in phases


# ── ISC taxonomy type coverage ────────────────────────────────────────────────

class TestTaxonomyTypeCoverage:
    def test_contains_hypothesis_generation_type(self):
        record = _make_record()
        disclosure = generate_isc_disclosure(record)
        types = {e.isc_type for e in disclosure.entries}
        assert "hypothesis_generation" in types

    def test_contains_documentation_type(self):
        record = _make_record()
        disclosure = generate_isc_disclosure(record)
        types = {e.isc_type for e in disclosure.entries}
        assert "documentation" in types

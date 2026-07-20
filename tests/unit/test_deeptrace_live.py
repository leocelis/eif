"""Tests for F4C3: DeepTRACE live source and citation verification.

New constraint in gap fix:
  F4C3: source_accuracy and citation_accuracy use live verification when a
        search_fn is provided; fall back to proxy when not.

This closes the gap between the proxy heuristic (V2 initial) and the actual
DeepTRACE audit methodology (arXiv:2509.04499) which checks real sources.
"""


from eif.record.research_object import (
    _verify_source_live,
    build_research_object,
    verify_sources_live,
)
from eif.schemas import (
    AssumptionRegistry,
    CalibrationResult,
    ChallengeResult,
    Claim,
    ProvenanceRecord,
)


def _make_record(
    claims: list[Claim] | None = None,
    sourced: bool = False,
) -> ProvenanceRecord:
    """Build a minimal ProvenanceRecord for testing."""
    if claims is None:
        if sourced:
            claims = [
                Claim(
                    text="Manor Lords has 36 IGDB hypes",
                    claim_type="GUESSED",
                    evidence_source="https://www.igdb.com/games/manor-lords",
                ),
                Claim(
                    text="Manor Lords has 78.4 total_rating",
                    claim_type="ASSUMED",
                    evidence_source="IGDB game database entry for Manor Lords",
                ),
            ]
        else:
            claims = [
                Claim(
                    text="Manor Lords has 3500 IGDB hypes",
                    claim_type="GUESSED",
                ),
            ]

    registry = AssumptionRegistry(
        session_id="test-dt",
        decision="Commission content on Manor Lords",
        guessed=[c for c in claims if c.claim_type == "GUESSED"],
        assumed=[c for c in claims if c.claim_type == "ASSUMED"],
    )

    return ProvenanceRecord(
        session_id="test-dt",
        decision="Commission content on Manor Lords",
        registry=registry,
        calibration=[
            CalibrationResult(
                claim_text="Manor Lords hypes",
                prior=0.5, likelihood=0.2, posterior=0.18,
                confidence_tier="LOW", prior_strategy="max_entropy",
            )
        ],
        challenge=ChallengeResult(
            claim_text="Manor Lords hypes",
            critic_model="gpt-4",
            critic_independence="DIFFERENT_OBJECTIVE",
            counter_evidence_found=True,
            counter_evidence=["IGDB real data: hypes=36"],
            verdict="DEFEATED",
        ),
        contrary_evidence_considered=True,
        tools_invoked=["eif_declare", "eif_challenge"],
        models_used=["gpt-4"],
    )


# ── F4C3: live verification activates when search_fn provided ─────────────────

class TestLiveVerificationActivation:
    def test_proxy_used_when_no_search_fn(self):
        record = _make_record(sourced=True)
        ro = build_research_object(record, verdict="HALT")
        # No CITATION_AUDIT flag when no live verification
        citation_flags = [f for f in ro.provenance_flags if "CITATION_AUDIT" in f]
        assert len(citation_flags) == 0

    def test_live_verification_runs_when_search_fn_provided(self):
        record = _make_record(sourced=True)
        search_calls = []

        def tracking_search(query: str) -> str:
            search_calls.append(query)
            return f"Result for: {query}. Manor Lords IGDB data: hypes 36 total_rating 78."

        build_research_object(record, verdict="HALT", search_fn=tracking_search)

        # search_fn should have been called at least once per sourced claim
        assert len(search_calls) >= 2  # 2 sourced claims

    def test_no_sourced_claims_returns_proxy_with_note(self):
        record = _make_record(sourced=False)
        search_calls = []

        def tracking_search(query: str) -> str:
            search_calls.append(query)
            return "result"

        ro = build_research_object(record, verdict="HALT", search_fn=tracking_search)

        # When no claims have evidence_source, search is not called (nothing to verify)
        assert len(search_calls) == 0
        # But a note about the limitation should appear in provenance_flags
        f4c3_notes = [f for f in ro.provenance_flags if "F4C3" in f or "CITATION_AUDIT" in f]
        assert len(f4c3_notes) >= 1


# ── _verify_source_live: per-claim verification ───────────────────────────────

class TestVerifySourceLive:
    def test_source_found_raises_score(self):
        """When search returns text matching the source, source_score should be high."""
        def confirming_search(query: str) -> str:
            return "igdb game manor lords hypes rating database verified"

        s_score, c_score = _verify_source_live(
            evidence_source="igdb.com manor lords database",
            claim_text="Manor Lords has 36 IGDB hypes",
            search_fn=confirming_search,
        )

        assert s_score >= 0.5

    def test_source_not_found_gives_low_score(self):
        """When search returns unrelated content, source_score should be low."""
        def unrelated_search(query: str) -> str:
            return "completely different topic about unrelated content nothing matches"

        s_score, c_score = _verify_source_live(
            evidence_source="igdb.com manor lords",
            claim_text="Manor Lords has 36 IGDB hypes",
            search_fn=unrelated_search,
        )

        assert s_score <= 0.5

    def test_contradiction_in_search_lowers_citation_score(self):
        """Contradiction signals in search results should lower citation_score."""
        def contradicting_search(query: str) -> str:
            return "IGDB hypes: 36. The claim of 3500 hypes is incorrect and wrong and false fabrication."

        s_score, c_score = _verify_source_live(
            evidence_source="igdb manor lords hypes",
            claim_text="Manor Lords has 3500 IGDB hypes",
            search_fn=contradicting_search,
        )

        # Citation score should be penalized by contradiction signals
        assert c_score <= 0.6

    def test_search_failure_returns_proxy_scores(self):
        """If search raises, scores fall back to 0.5."""
        def failing_search(query: str) -> str:
            raise RuntimeError("network error")

        s_score, c_score = _verify_source_live(
            evidence_source="some source",
            claim_text="some claim",
            search_fn=failing_search,
        )

        assert s_score == 0.5
        assert c_score == 0.5


# ── verify_sources_live: multi-claim aggregation ──────────────────────────────

class TestVerifySourcesLiveAggregation:
    def test_returns_three_tuple(self):
        record = _make_record(sourced=True)

        def search(q: str) -> str:
            return f"result for {q}"

        source_acc, citation_acc, notes = verify_sources_live(record, search)

        assert isinstance(source_acc, float)
        assert isinstance(citation_acc, float)
        assert isinstance(notes, list)
        assert 0.0 <= source_acc <= 1.0
        assert 0.0 <= citation_acc <= 1.0

    def test_notes_include_verdict_per_claim(self):
        record = _make_record(sourced=True)

        def search(q: str) -> str:
            return "igdb manor lords hypes rating total_rating"

        _, _, notes = verify_sources_live(record, search)

        # Each note should mention VERIFIED or UNVERIFIED
        for note in notes:
            assert "VERIFIED" in note or "UNVERIFIED" in note

    def test_no_sourced_claims_returns_proxy_tuple(self):
        record = _make_record(sourced=False)

        def search(q: str) -> str:
            return "result"

        source_acc, citation_acc, notes = verify_sources_live(record, search)

        assert len(notes) == 1
        assert "F4C3" in notes[0]

    def test_verified_dimensions_appear_in_research_object_flags(self):
        """UNVERIFIED citations should appear as CITATION_AUDIT flags."""
        record = _make_record(sourced=True)

        def contradicting_search(q: str) -> str:
            return "false wrong incorrect fabricated not found unrelated"

        ro = build_research_object(record, verdict="HALT", search_fn=contradicting_search)

        audit_flags = [f for f in ro.provenance_flags if "CITATION_AUDIT" in f]
        assert len(audit_flags) >= 1

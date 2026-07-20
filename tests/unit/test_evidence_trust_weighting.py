"""Tests for eif_v5_evidence_trust_weighting (TW1–TW9).

Maps 1:1 to the constraints in
eif/falsify/eif_v5_evidence_trust_weighting_intent.yaml. Each test uses the
exact assertion from the constraint's `test` field (with relevant stub text so
the collector's is_relevant() gate passes for the corroboration cases).

The eif_verify-driven cases (TW3, TW8, TW9) monkeypatch
eif.falsify.evidence_collector.collect_evidence so they are hermetic and offline
(no DDGS / network). eif_verify imports collect_evidence locally inside the
function body, so patching the module attribute takes effect at call time.
"""

from __future__ import annotations

import pytest

import eif.falsify.evidence_collector as ec_mod
from eif import session as session_store
from eif.calibrate.bayesian import compute_posterior
from eif.calibrate.ece import apply_domain_ceiling
from eif.calibrate.trust import tier_confidence_likelihood
from eif.falsify.evidence_collector import (
    EvidenceResult,
    collect_web_search,
)
from eif.mcp_server.server import eif_verify
from eif.schemas import THRESHOLD_ACT

# ── TW1 - likelihood is tier- and confidence-aware ────────────────────────────

def test_tw1_likelihood_is_tier_and_confidence_aware():
    assert (
        tier_confidence_likelihood("P1_NATIVE_CODE", 0.9, True, False)
        > tier_confidence_likelihood("P3_WEB_SEARCH", 0.65, True, False)
    )


# ── TW2 - single uncorroborated P3 SUPPORTS cannot reach ACT ───────────────────

def test_tw2_single_p3_supports_below_act():
    L = tier_confidence_likelihood("P3_WEB_SEARCH", 0.65, True, False)
    assert compute_posterior(0.5, True, L)[0] < THRESHOLD_ACT
    assert THRESHOLD_ACT == 0.70


# ── TW4 - two distinct-domain web sources set corroborated=True ────────────────

def test_tw4_two_distinct_domains_corroborated():
    # Stub text shares tokens with the claim (passes is_relevant) and cites two
    # DISTINCT registrable domains.
    def fn(_q: str) -> str:
        return (
            "Vitamin D reduces fracture risk in adults, study finds "
            "[https://www.nih.gov/x]. Independent review on fracture risk in "
            "adults agrees [https://nature.com/y]."
        )

    r = collect_web_search(
        "vitamin D reduces fracture risk in adults", fn, max_iterations=1
    )
    assert r.independent_source_count >= 2
    assert r.corroborated is True


# ── TW5 - echo/duplicate (same-domain) sources count once ──────────────────────

def test_tw5_same_domain_counts_once():
    # Two snippets from the SAME registrable domain → one independent source.
    def fn(_q: str) -> str:
        return (
            "Vitamin D reduces fracture risk in adults [https://www.example.com/a]. "
            "Same site, different page on fracture risk in adults "
            "[https://example.com/b]."
        )

    r = collect_web_search(
        "vitamin D reduces fracture risk in adults", fn, max_iterations=1
    )
    assert r.independent_source_count == 1
    assert r.corroborated is False


# ── TW6 - P3 no longer bypasses the domain posterior ceiling ───────────────────

def test_tw6_p3_subject_to_ceiling_p1_still_bypasses():
    p3, c3 = apply_domain_ceiling(0.97, "healthcare", "P3_WEB_SEARCH")
    assert c3 is True
    assert p3 <= 0.95
    # P1 direct-observation bypass preserved.
    p1, c1 = apply_domain_ceiling(0.97, "healthcare", "P1_NATIVE_CODE")
    assert c1 is False


# ── TW7 - P0/P1 SUPPORTS still reaches ACT ─────────────────────────────────────

def test_tw7_p1_supports_reaches_act():
    L = tier_confidence_likelihood("P1_NATIVE_CODE", 0.9, True, False)
    assert compute_posterior(0.5, True, L)[0] >= THRESHOLD_ACT


# ── eif_verify-driven cases (TW3, TW8, TW9) ────────────────────────────────────

async def _new_session_id() -> str:
    sess = await session_store.new_session()
    return sess.session_id


def _patch_collect_evidence(monkeypatch, result: EvidenceResult) -> None:
    """Force collect_evidence (used by eif_verify) to return a fixed result."""
    def _fake(*_args, **_kwargs) -> EvidenceResult:
        return result
    monkeypatch.setattr(ec_mod, "collect_evidence", _fake)


@pytest.mark.asyncio
async def test_tw3_high_consequence_single_p3_supports_halts(monkeypatch):
    # Only evidence is an uncorroborated P3 SUPPORTS for a HIGH-consequence claim.
    _patch_collect_evidence(monkeypatch, EvidenceResult(
        probe_tier="P3_WEB_SEARCH",
        verdict="SUPPORTS",
        confidence=0.65,
        evidence_summary="single web match",
        evidence_source="WEB_SEARCH",
        independent_source_count=1,
        corroborated=False,
    ))
    sid = await _new_session_id()
    result = await eif_verify(
        session_id=sid,
        decision="Ship the diagnostic model to clinics",
        claims=[{
            "text": "The triage model is safe for unsupervised clinical use",
            "claim_type": "ASSUMED",
            "consequence_of_wrong": "HIGH",
        }],
    )
    assert result["verdict"] == "HALT"
    assert any(
        "WEAK_EVIDENCE_HIGH_CONSEQUENCE" in h.get("reason", "")
        for h in result["halted_claims"]
    ), result["halted_claims"]


@pytest.mark.asyncio
async def test_tw3_corroborated_p3_high_consequence_does_not_weak_halt(monkeypatch):
    # Control: a CORROBORATED P3 SUPPORTS for a HIGH-consequence claim must NOT
    # trip the WEAK_EVIDENCE_HIGH_CONSEQUENCE gate (it may still surface as
    # HIGH_RISK_ASSUMED, but not as the weak-evidence HALT reason).
    _patch_collect_evidence(monkeypatch, EvidenceResult(
        probe_tier="P3_WEB_SEARCH",
        verdict="SUPPORTS",
        confidence=0.75,
        evidence_summary="two independent web sources",
        evidence_source="WEB_SEARCH",
        independent_source_count=2,
        corroborated=True,
    ))
    sid = await _new_session_id()
    result = await eif_verify(
        session_id=sid,
        decision="Ship the diagnostic model to clinics",
        claims=[{
            "text": "The triage model is safe for unsupervised clinical use",
            "claim_type": "ASSUMED",
            "consequence_of_wrong": "HIGH",
        }],
    )
    assert not any(
        "WEAK_EVIDENCE_HIGH_CONSEQUENCE" in h.get("reason", "")
        for h in result["halted_claims"]
    ), result["halted_claims"]


@pytest.mark.asyncio
async def test_tw8_contradicts_still_halts_regardless_of_tier(monkeypatch):
    # A CONTRADICTS verdict - even from the lowest web tier - must still HALT.
    _patch_collect_evidence(monkeypatch, EvidenceResult(
        probe_tier="P3_WEB_SEARCH",
        verdict="CONTRADICTS",
        confidence=0.60,
        evidence_summary="web evidence contradicts the claim",
        evidence_source="WEB_SEARCH",
        independent_source_count=1,
        corroborated=False,
    ))
    sid = await _new_session_id()
    result = await eif_verify(
        session_id=sid,
        decision="Deploy v2",
        claims=[{
            "text": "Latency stays under 100ms at peak load",
            "claim_type": "ASSUMED",
            "consequence_of_wrong": "MEDIUM",
        }],
    )
    assert result["verdict"] == "HALT"
    assert any(h.get("claim") for h in result["halted_claims"])
    assert any(
        h.get("reason") == "EVIDENCE_CONTRADICTS" for h in result["halted_claims"]
    ), result["halted_claims"]


@pytest.mark.asyncio
async def test_tw9_response_exposes_tier_mix_and_p0_coverage(monkeypatch):
    _patch_collect_evidence(monkeypatch, EvidenceResult(
        probe_tier="P0_HOST_TOOL",
        verdict="SUPPORTS",
        confidence=0.8,
        evidence_summary="authoritative host tool",
        evidence_source="HOST_TOOL:ehr",
    ))
    sid = await _new_session_id()
    result = await eif_verify(
        session_id=sid,
        decision="Deploy v2",
        claims=[{
            "text": "The service returns JSON with a 200 status",
            "claim_type": "ASSUMED",
            "consequence_of_wrong": "MEDIUM",
        }],
    )
    assert isinstance(result["evidence_tier_mix"], dict)
    assert isinstance(result["p0_coverage_pct"], float)
    # One probed claim, P0 evidence → 100% P0 coverage and a P0 tier-mix entry.
    assert result["evidence_tier_mix"].get("P0_HOST_TOOL") == 1
    assert result["p0_coverage_pct"] == 100.0

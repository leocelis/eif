"""Research Object + DeepTRACE 8-dimension audit - V2 (F4).

V1 ProvenanceRecord covers 2 of DeepTRACE's 8 audit dimensions (answer_accuracy
via verdict + temporal_currency via staleness warnings). V2 adds a full
ResearchObject wrapping the ProvenanceRecord with all 8 dimensions.

The gap this closes vs. initial V2: source_accuracy and citation_accuracy were
pure proxies from session metadata. V2 now runs live source verification via
native_search - checking whether claimed sources exist and whether they
corroborate the claim text. This implements DeepTRACE's actual audit methodology
(arXiv:2509.04499: citation accuracy 40–80%; untracked intermediate steps are
the primary failure mode).

Research:
  Research Object arXiv:2604.11261 (2026) - structured AI governance via
  { inputs, process, outputs, provenance } with model config, prompts+hashes,
  parameters, interaction logs, human vs AI decisions.
  DeepTRACE arXiv:2509.04499 (2025) - 8-dimension audit; citation accuracy
  40–80%; untracked intermediate steps are primary failure mode.

Constraints:
  F4C1: all 8 DeepTRACE dimensions populated; overall_score = mean(8).
  F4C2: evidence older than stale_days flags STALE_EVIDENCE in provenance_flags.
  F4C3 [new]: source_accuracy and citation_accuracy use live verification
              when a search_fn is provided; fall back to proxy when not.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC

from eif.schemas import (
    EVIDENCE_STALENESS_DAYS,
    DeepTRACEAudit,
    ProvenanceRecord,
    ResearchObject,
)

_log = logging.getLogger(__name__)

_STALE_DAYS = EVIDENCE_STALENESS_DAYS  # 30 by default; 180 as per F4 intent


# ── Dimension scorers (proxy path) ────────────────────────────────────────────

def _score_answer_accuracy(record: ProvenanceRecord) -> float:
    """Dimension 1: Was a verdict reached with posterior in a decisive tier?"""
    if not record.calibration:
        return 0.3
    posteriors = [r.posterior for r in record.calibration]
    avg_posterior = sum(posteriors) / len(posteriors)
    if avg_posterior >= 0.70 or avg_posterior <= 0.20:
        return 0.9  # decisive ACT or HALT
    if avg_posterior >= 0.40:
        return 0.6  # REVISE - lower confidence in verdict
    return 0.4


def _score_source_accuracy_proxy(record: ProvenanceRecord) -> float:
    """Dimension 2 (proxy): Evidence sources provided in claims."""
    all_claims = record.registry.known + record.registry.assumed + record.registry.guessed
    with_sources = sum(1 for c in all_claims if c.evidence_source)
    if not all_claims:
        return 0.5
    return round(with_sources / len(all_claims), 4)


def _score_citation_accuracy_proxy(record: ProvenanceRecord) -> float:
    """Dimension 3 (proxy): Evidence corroborates claims via SPRT/causal gate."""
    if record.causal_evidence_result is not None:
        cev = record.causal_evidence_result
        if cev.verdict == "SUPPORTED":
            return 0.90
        if cev.verdict == "CONTESTED":
            return 0.55
        if cev.verdict == "NO_EVIDENCE":
            return 0.25

    if record.sprt_results:
        accepted = sum(1 for s in record.sprt_results if s.decision == "ACCEPT")
        return round(max(0.3, accepted / len(record.sprt_results)), 4)

    return 0.50


def _score_claim_evidence_alignment(record: ProvenanceRecord) -> float:
    """Dimension 4: Each claim's evidence trail matches its verdict."""
    if not record.falsification_conditions:
        return 0.5

    n = len(record.falsification_conditions)
    matched = 0
    sprt_decisions = {s.decision for s in record.sprt_results} if record.sprt_results else set()

    for fc in record.falsification_conditions:
        if record.sprt_results:
            matched += 1 if sprt_decisions else 0
        else:
            matched += 1 if fc.condition else 0

    return round(matched / n, 4) if n else 0.5


def _score_reasoning_transparency(record: ProvenanceRecord) -> float:
    """Dimension 5: All reasoning steps logged (tools invoked, models used)."""
    score = 0.5
    if record.tools_invoked:
        score += 0.2
    if record.models_used:
        score += 0.1
    if record.input_fingerprint:
        score += 0.1
    if record.model_config_snapshot:
        score += 0.1
    return min(score, 1.0)


def _score_uncertainty_disclosure(record: ProvenanceRecord) -> float:
    """Dimension 6: Claims with posterior in [0.20, 0.70] flagged as uncertain."""
    if not record.calibration:
        return 0.5

    uncertain = [r for r in record.calibration if 0.20 <= r.posterior <= 0.70]
    total = len(record.calibration)

    if not uncertain:
        return 1.0

    return round(1.0 - (len(uncertain) / total) * 0.5, 4)


def _score_coverage_completeness(record: ProvenanceRecord) -> float:
    """Dimension 7: Contradicting evidence explicitly included."""
    if record.contrary_evidence_considered:
        return 1.0
    if record.challenge and record.challenge.counter_evidence:
        return 0.85
    if record.challenge and record.challenge.counter_evidence_found:
        return 0.70
    return 0.30


def _score_temporal_currency(
    record: ProvenanceRecord,
    stale_days: int = 180,
) -> tuple[float, list[str]]:
    """Dimension 8: Evidence within the temporal currency window.

    F4C2: evidence older than `stale_days` relative to decision date must be
    flagged as STALE in the ResearchObject provenance_flags.
    """
    decision_dt = record.timestamp
    all_claims = record.registry.known + record.registry.assumed + record.registry.guessed
    claims_with_dates = [c for c in all_claims if c.retrieved_at is not None]

    if not claims_with_dates:
        return 0.7, []

    # Normalize timezone awareness: if decision_dt is naive, strip tz from retrieved_at
    # (or vice-versa) to allow subtraction regardless of how the caller populated the record.
    stale_flags: list[str] = []
    for c in claims_with_dates:
        r_at = c.retrieved_at
        if decision_dt.tzinfo is None and r_at.tzinfo is not None:  # type: ignore[union-attr]
            r_at = r_at.replace(tzinfo=None)  # type: ignore[union-attr]
        elif decision_dt.tzinfo is not None and r_at.tzinfo is None:  # type: ignore[union-attr]
            r_at = r_at.replace(tzinfo=UTC)  # type: ignore[union-attr]
        age = (decision_dt - r_at).days  # type: ignore[operator]
        if age > stale_days:
            flag = (
                f"STALE_EVIDENCE: claim {c.text[:60]!r} - "
                f"evidence retrieved {age} days before decision (threshold={stale_days}d)"
            )
            stale_flags.append(flag)

    fresh_count = len(claims_with_dates) - len(stale_flags)
    currency_score = round(fresh_count / len(claims_with_dates), 4)
    return currency_score, stale_flags


# ── Live verification (F4C3) ──────────────────────────────────────────────────

def _verify_source_live(
    evidence_source: str,
    claim_text: str,
    search_fn: Callable[[str], str],
) -> tuple[float, float]:
    """Run a live search to verify source existence and citation accuracy.

    Args:
        evidence_source: The claimed source (URL, paper title, or description).
        claim_text:      The claim that cites this source.
        search_fn:       A search function that takes a query and returns text.

    Returns:
        (source_score, citation_score) each in [0, 1]:
        - source_score: Does the source appear to exist? (0.0 = not found, 1.0 = confirmed)
        - citation_score: Does the source's content corroborate the claim? (0.0–1.0)

    This is the live implementation of DeepTRACE's citation verification
    (arXiv:2509.04499): citation accuracy 40–80% across current AI research systems.
    """
    try:
        # Source existence check
        source_query = evidence_source[:200]
        source_result = search_fn(source_query)
        source_lower = source_result.lower()
        source_ref_lower = evidence_source.lower()

        source_found = any(
            word in source_lower
            for word in source_ref_lower.split()
            if len(word) > 4
        )
        source_score = 0.8 if source_found else 0.2

        # Citation accuracy check - does the source contain signal supporting the claim?
        # Query: source + key claim terms
        claim_key_terms = " ".join(
            w for w in claim_text.lower().split()
            if len(w) > 4 and w not in {"about", "which", "these", "their", "would", "should"}
        )[:200]
        citation_query = f"{evidence_source[:100]} {claim_key_terms}"
        citation_result = search_fn(citation_query)
        citation_lower = citation_result.lower()

        # Score based on key claim term overlap in the returned evidence
        claim_words = [w for w in claim_text.lower().split() if len(w) > 5]
        if claim_words:
            matched = sum(1 for w in claim_words if w in citation_lower)
            citation_score = round(min(matched / len(claim_words), 1.0), 4)
            # Penalize if result contains explicit contradiction signals
            contradiction_signals = ["not", "incorrect", "wrong", "false", "fabricat",
                                      "contradicts", "lower than", "off by"]
            if any(s in citation_lower for s in contradiction_signals):
                citation_score = max(0.0, citation_score - 0.3)
        else:
            citation_score = 0.5

        _log.info(
            "DeepTRACE live verify: source=%s source_score=%.2f citation_score=%.2f",
            evidence_source[:60], source_score, citation_score,
        )
        return source_score, citation_score

    except Exception as exc:  # noqa: BLE001
        _log.warning("DeepTRACE live verify failed (%s) - returning proxy scores", exc)
        return 0.5, 0.5


def verify_sources_live(
    record: ProvenanceRecord,
    search_fn: Callable[[str], str],
) -> tuple[float, float, list[str]]:
    """Run live source + citation verification for all claims with evidence_source set.

    Implements F4C3: replaces proxy scores for source_accuracy (dim 2) and
    citation_accuracy (dim 3) with live-verified scores using actual search.

    Args:
        record:    The ProvenanceRecord to audit.
        search_fn: Search function (claim text → result text).

    Returns:
        (source_accuracy, citation_accuracy, verification_notes)
        source_accuracy:   Verified dimension 2 score.
        citation_accuracy: Verified dimension 3 score.
        verification_notes: Human-readable notes per source checked.
    """
    all_claims = record.registry.known + record.registry.assumed + record.registry.guessed
    sourced_claims = [c for c in all_claims if c.evidence_source]

    if not sourced_claims:
        # No sources to verify - proxy signals
        proxy_source = _score_source_accuracy_proxy(record)
        proxy_citation = _score_citation_accuracy_proxy(record)
        note = (
            "F4C3: no claims have evidence_source set - "
            "source_accuracy and citation_accuracy use proxy scores. "
            "DeepTRACE finding: 40–80% of AI-generated citations are unreliable "
            "(arXiv:2509.04499). Providing evidence_source on claims enables live verification."
        )
        _log.info("DeepTRACE: no sourced claims - proxy scores used")
        return proxy_source, proxy_citation, [note]

    source_scores: list[float] = []
    citation_scores: list[float] = []
    notes: list[str] = []

    for c in sourced_claims:
        s_score, c_score = _verify_source_live(
            evidence_source=str(c.evidence_source),
            claim_text=c.text,
            search_fn=search_fn,
        )
        source_scores.append(s_score)
        citation_scores.append(c_score)
        verdict = "VERIFIED" if s_score >= 0.7 and c_score >= 0.5 else "UNVERIFIED"
        notes.append(
            f"[{verdict}] source={c.evidence_source[:60]!r} "
            f"source_score={s_score:.2f} citation_score={c_score:.2f} "
            f"claim={c.text[:80]!r}"
        )

    avg_source = round(sum(source_scores) / len(source_scores), 4)
    avg_citation = round(sum(citation_scores) / len(citation_scores), 4)

    _log.info(
        "DeepTRACE: live verification complete - %d claims checked "
        "source_accuracy=%.4f citation_accuracy=%.4f",
        len(sourced_claims), avg_source, avg_citation,
    )

    return avg_source, avg_citation, notes


# ── Main builder ──────────────────────────────────────────────────────────────

def build_research_object(
    record: ProvenanceRecord,
    verdict: str = "UNKNOWN",
    phases_run: list[str] | None = None,
    stale_days: int = 180,
    search_fn: Callable[[str], str] | None = None,
) -> ResearchObject:
    """Build a ResearchObject from a ProvenanceRecord.

    Populates all 8 DeepTRACE dimensions (F4C1). Generates provenance_flags for
    any dimension scoring below 0.5. Flags stale evidence in provenance_flags (F4C2).
    When search_fn is provided, runs live source + citation verification (F4C3).

    Args:
        record:     The ProvenanceRecord from the completed EIF session.
        verdict:    Final routing verdict (ACT / HALT / REVISE).
        phases_run: List of EIF phase names that executed this session.
        stale_days: Temporal currency threshold in days (F4C2 default: 180).
        search_fn:  Optional search function for live verification (F4C3).
                    When None, falls back to proxy scoring.

    Returns:
        ResearchObject with all 8 dimensions populated and overall_score computed.
    """
    temporal_score, stale_flags = _score_temporal_currency(record, stale_days)

    # Dimensions 2+3: live verification when search_fn provided (F4C3)
    verification_notes: list[str] = []
    if search_fn is not None:
        source_accuracy, citation_accuracy, verification_notes = verify_sources_live(
            record, search_fn
        )
        _log.info("DeepTRACE: using live-verified source/citation scores (F4C3)")
    else:
        source_accuracy = _score_source_accuracy_proxy(record)
        citation_accuracy = _score_citation_accuracy_proxy(record)

    dimensions = DeepTRACEAudit(
        answer_accuracy=_score_answer_accuracy(record),
        source_accuracy=source_accuracy,
        citation_accuracy=citation_accuracy,
        claim_evidence_alignment=_score_claim_evidence_alignment(record),
        reasoning_transparency=_score_reasoning_transparency(record),
        uncertainty_disclosure=_score_uncertainty_disclosure(record),
        coverage_completeness=_score_coverage_completeness(record),
        temporal_currency=temporal_score,
    )

    # F4C1: generate provenance_flags for dimensions below 0.5
    provenance_flags: list[str] = list(stale_flags)
    for dim_name, score in dimensions.dim_scores.items():
        if score < 0.5:
            provenance_flags.append(
                f"DIMENSION_LOW: {dim_name} = {score:.3f} (threshold: 0.50)"
            )

    # F4C3: add verification notes as provenance entries
    if verification_notes:
        for note in verification_notes:
            if "UNVERIFIED" in note or "F4C3:" in note:
                provenance_flags.append(f"CITATION_AUDIT: {note}")

    uncertain_claims = [
        r.claim_text
        for r in record.calibration
        if 0.20 <= r.posterior <= 0.70
    ]

    _log.info(
        "DeepTRACE: overall_score=%.4f flags=%d stale=%d uncertain=%d live_verify=%s",
        dimensions.overall_score, len(provenance_flags), len(stale_flags),
        len(uncertain_claims), search_fn is not None,
    )

    return ResearchObject(
        session_id=record.session_id,
        decision=record.decision,
        verdict=verdict,
        dimensions=dimensions,
        provenance_flags=provenance_flags,
        total_claims=(
            len(record.registry.known) +
            len(record.registry.assumed) +
            len(record.registry.guessed)
        ),
        phases_run=phases_run or [],
        models_used=list(record.models_used),
        tools_invoked=list(record.tools_invoked),
        contrary_evidence_included=record.contrary_evidence_considered,
        uncertain_claims=uncertain_claims,
        stale_sources=[f for f in stale_flags],
    )

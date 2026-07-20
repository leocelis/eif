"""ISC Global Reporting Standard - AI Disclosure Taxonomy - V2 (F5).

Maps EIF pipeline phases to ISC taxonomy entries, generating a structured
disclosure of how AI was used in each phase of the epistemic verification
process.

Status: ISC_DRAFT_COMPLIANCE - the ISC standard is in public consultation
through 2026 and will finalize 2026-2027. This implementation conforms to
the draft taxonomy (OI3 in eif_v2_intent.yaml).

Research:
  ISC Global Reporting Standard for AI in Research (2026 draft)
  https://council.science/our-work/ai-disclosure-in-research/
  Taxonomy types (CRediT analogy): hypothesis_generation, data_collection,
  analysis, peer_review, documentation, human_review, human_required.

F5C1: ≥ 1 entry per EIF pipeline phase that ran.
F5C2: HALT verdict must include a human_required entry.
"""

from __future__ import annotations

import logging

from eif.schemas import ISCDisclosure, ISCDisclosureEntry, ProvenanceRecord

_log = logging.getLogger(__name__)

# Phase → ISC taxonomy mapping.
# Each tuple: (eif_phase, isc_type, default_model_description, task_description)
_PHASE_MAP: list[tuple[str, str, str, str, str | None]] = [
    # (phase, isc_type, model_label, task_desc, human_review_step)
    (
        "DECLARE",
        "hypothesis_generation",
        "EIF AssumptionRegistry",
        "Extract and classify claims (KNOWN/ASSUMED/GUESSED) from the decision statement.",
        None,
    ),
    (
        "FALSIFY",
        "data_collection",
        "EIF native_search (DDGS P3) / AST-screened template code execution (P1)",
        "Collect falsifying evidence via web search and code execution probes.",
        None,
    ),
    (
        "FALSIFY_ANALYSIS",
        "analysis",
        "EIF SPRT engine",
        "Apply Sequential Probability Ratio Test to evidence observations.",
        None,
    ),
    (
        "CAUSAL_GATE",
        "analysis",
        "EIF CausalGate v4 / IRIS pipeline",
        "Classify causal level on Pearl hierarchy; discover confounders via IRIS.",
        None,
    ),
    (
        "CALIBRATE",
        "analysis",
        "EIF Bayesian calibrator",
        "Compute posterior probability via Bayes' theorem; apply ECE correction.",
        None,
    ),
    (
        "CHALLENGE",
        "peer_review",
        "EIF multi-critic / DASES replicator",
        "Adversarial review: search for counter-evidence and competing hypotheses.",
        "Human should verify critic independence before acting on challenge results.",
    ),
    (
        "SYCOPHANCY_GATE",
        "analysis",
        "EIF SycophancyDetector (MONICA/ELEPHANT)",
        "Detect position drift, face-preserving framing, and unfaithful reasoning.",
        None,
    ),
    (
        "UPDATE",
        "analysis",
        "EIF Bayesian posterior updater",
        "Update posterior with new evidence; compute EIG; apply stopping rules.",
        None,
    ),
    (
        "EXPLAIN",
        "documentation",
        "EIF ExplanationArtifact",
        "Generate hard-to-vary explanation and testable predictions.",
        None,
    ),
    (
        "RECORD",
        "documentation",
        "EIF ProvenanceRecord",
        "Assemble full provenance chain with fingerprint, models, and tools used.",
        None,
    ),
    (
        "PROGRAMME",
        "analysis",
        "EIF Lakatos programme monitor",
        "Assess research programme health: progressive/stable/degenerative.",
        None,
    ),
    (
        "HYPOTHESIS_AGENDA",
        "hypothesis_generation",
        "EIF HypothesisAgenda scorer (EIG + FDR)",
        "Rank hypotheses by expected information gain with FDR correction.",
        None,
    ),
    (
        "INPUT_GUARD",
        "analysis",
        "EIF InputGuard (framing + injection detector)",
        "Detect adversarial prompt injection and framing before processing.",
        None,
    ),
]

# Phases that indicate a human decision point when the verdict is HALT
_HALT_TRIGGER_PHASES = {"CALIBRATE", "CHALLENGE", "SYCOPHANCY_GATE", "CAUSAL_GATE"}


def generate_isc_disclosure(
    record: ProvenanceRecord,
    verdict: str = "UNKNOWN",
    phases_run: list[str] | None = None,
    models_used: list[str] | None = None,
) -> ISCDisclosure:
    """Generate ISC-compliant AI disclosure from a completed EIF session.

    Args:
        record:      The session's ProvenanceRecord.
        verdict:     Final routing verdict (ACT / HALT / REVISE).
        phases_run:  List of EIF phases that executed this session.
                     If None, inferred from record contents via _infer_phases().
        models_used: Override model names for disclosure entries.

    Returns:
        ISCDisclosure with ≥ 1 entry per phase and human_required on HALT (F5C1/F5C2).

    Note (R7-08): SYCOPHANCY_GATE is not stored as a dedicated ProvenanceRecord field
    (it runs in-process and is session-local). When called via eif_record in the MCP
    server, SYCOPHANCY_GATE is injected into phases_run from the session-level
    _sycophancy_gates registry. Callers using generate_isc_disclosure() directly
    should pass phases_run explicitly to guarantee SYCOPHANCY_GATE appears in the
    disclosure when that gate ran.
    """
    # Infer phases from record when not explicitly provided or when empty list supplied.
    # An empty list would cause phases_set to be falsy, bypassing the filter and emitting
    # every phase - violating F5C1 ("at least one entry per phase that ran").
    if not phases_run:
        phases_run = _infer_phases(record)

    phases_set = set(phases_run)
    entries: list[ISCDisclosureEntry] = []

    model_names = models_used or record.models_used or []
    primary_model = model_names[0] if model_names else "EIF engine"

    for (phase, isc_type, default_model, task, human_review) in _PHASE_MAP:
        # R9-01: only include phases that actually ran.
        # DECLARE and RECORD are always-run and are always added by _infer_phases(), so they
        # will be in phases_set. Exempting only them here is safe and semantically correct.
        # CALIBRATE and FALSIFY were previously over-exempted - they must obey phases_set.
        if phases_set and phase not in phases_set and phase + "_ANALYSIS" not in phases_set:
            if phase not in {"DECLARE", "RECORD"}:
                continue

        # Use primary model name for agent-driven phases; keep default_model label otherwise
        model_for_phase = primary_model if isc_type in ("analysis", "peer_review") else default_model

        entries.append(ISCDisclosureEntry(
            eif_phase=phase,
            isc_type=isc_type,  # type: ignore[arg-type]
            model_name=model_for_phase,
            task_description=task,
            human_review_step=human_review,
            isc_draft_compliance=True,
        ))

    # F5C2: HALT verdict must include a human_required entry
    if verdict.upper() == "HALT":
        entries.append(ISCDisclosureEntry(
            eif_phase="HALT_DECISION",
            isc_type="human_required",
            model_name="human",
            task_description=(
                "EIF issued a HALT verdict. The decision must not be acted upon without "
                "explicit human review of the flagged claims and evidence."
            ),
            human_review_step=(
                "Review HALT-flagged claims. Verify evidence independently before proceeding. "
                "Document the human review outcome in the session record."
            ),
            isc_draft_compliance=True,
        ))
        _log.info("ISC: HALT verdict - added human_required disclosure entry")

    _log.info(
        "ISC disclosure generated: %d entries for session=%s verdict=%s [ISC_DRAFT_COMPLIANCE]",
        len(entries), record.session_id, verdict,
    )

    return ISCDisclosure(
        session_id=record.session_id,
        entries=entries,
        isc_version="draft-2026",
    )


def _infer_phases(record: ProvenanceRecord) -> list[str]:
    """Infer which EIF phases ran from record contents.

    R6-13: also checks input_guard field (IG6) and tools_invoked for SYCOPHANCY_GATE
    so those phases appear in the ISC disclosure when they ran.
    """
    phases = ["DECLARE"]  # always runs

    # INPUT_GUARD: persisted on ProvenanceRecord via assemble_record (IG6)
    if record.input_guard is not None:
        phases.append("INPUT_GUARD")

    if record.falsification_conditions or record.sprt_results:
        phases.append("FALSIFY")
        phases.append("FALSIFY_ANALYSIS")

    if record.causal_gate is not None:
        phases.append("CAUSAL_GATE")

    if record.calibration:
        phases.append("CALIBRATE")

    # SYCOPHANCY_GATE: not stored as a dedicated ProvenanceRecord field, but may appear
    # in tools_invoked when the caller explicitly listed it; also inferred from models_used
    # heuristic (eif_sycophancy_gate runs in-process, leaves no record artifact).
    if any("sycophancy" in t.lower() for t in (record.tools_invoked or [])):
        phases.append("SYCOPHANCY_GATE")

    if record.challenge is not None:
        phases.append("CHALLENGE")

    if record.updates:
        phases.append("UPDATE")

    if record.explanation is not None:
        phases.append("EXPLAIN")

    phases.append("RECORD")  # always runs at end

    return phases

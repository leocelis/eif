"""EIF schemas - Pydantic v2 models and constants.

This is the dependency root. Every other EIF module imports from here.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

ENGINE_VERSION = "4.1.0"

# Decision thresholds
THRESHOLD_ACT: float = 0.70
THRESHOLD_REVISE: float = 0.40
THRESHOLD_HALT: float = 0.20

# EIG stopping threshold (nats)
EIG_THRESHOLD: float = 0.01

# Evidence staleness (days)
EVIDENCE_STALENESS_DAYS: int = 30

# Conformal prediction minimum calibration history
CONFORMAL_MIN_HISTORY: int = 20

# Prior strategy selection threshold
PRIOR_EMPIRICAL_MIN: int = 10

# Replication verdict thresholds
REPLICATE_AGREE_THRESHOLD: float = 0.80
REPLICATE_FAIL_THRESHOLD: float = 0.50


# ─────────────────────────────────────────────
# 2.1  Claim - the atomic epistemic unit
# ─────────────────────────────────────────────

ClaimType = Literal["KNOWN", "ASSUMED", "GUESSED"]
RiskLevel = Literal["HIGH", "MEDIUM", "LOW"]


ClaimMode = Literal["EXPLORATORY", "CONFIRMATORY", "UNSPECIFIED"]


class Claim(BaseModel):
    text: str
    claim_type: ClaimType
    basis: str | None = None
    evidence_source: str | None = None
    falsification_condition: str | None = None
    consequence_of_wrong: RiskLevel = "MEDIUM"
    verified_at: datetime | None = None
    retrieved_at: datetime | None = None
    claim_mode: ClaimMode = "UNSPECIFIED"

    @field_validator("evidence_source")
    @classmethod
    def known_must_have_source(cls, v, info):
        if info.data.get("claim_type") == "KNOWN" and not v:
            raise ValueError("KNOWN claims must have an evidence_source")
        return v


class ClaimInput(BaseModel):
    text: str
    claim_type: ClaimType
    basis: str | None = None
    evidence_source: str | None = None
    falsification_condition: str | None = None
    consequence_of_wrong: RiskLevel = "MEDIUM"
    retrieved_at: datetime | None = None
    claim_mode: ClaimMode = "UNSPECIFIED"

    @field_validator("evidence_source")
    @classmethod
    def known_must_have_source(cls, v, info):
        if info.data.get("claim_type") == "KNOWN" and not v:
            raise ValueError("KNOWN claims must have an evidence_source")
        return v


# ─────────────────────────────────────────────
# 2.2  AssumptionRegistry - Phase 1 output
# ─────────────────────────────────────────────


class AssumptionRegistry(BaseModel):
    session_id: str
    decision: str
    known: list[Claim] = Field(default_factory=list)
    assumed: list[Claim] = Field(default_factory=list)
    guessed: list[Claim] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    harking_flag: bool = False
    # ENGINE C13 V3: reasons populated by detect_harking() when harking_flag=True.
    harking_reasons: list[str] = Field(default_factory=list)

    @property
    def high_risk_assumed(self) -> list[Claim]:
        """Top claims by consequence for the Assumption Check Card."""
        at_risk = [c for c in self.assumed + self.guessed
                   if c.consequence_of_wrong == "HIGH"]
        return sorted(at_risk, key=lambda c: c.claim_type)[:3]


# ─────────────────────────────────────────────
# 2.3  FalsificationCondition - Phase 2 structure
# ─────────────────────────────────────────────

SPRTDecision = Literal["ACCEPT", "REJECT", "CONTINUE"]


class FalsificationCondition(BaseModel):
    claim_text: str
    condition: str
    threshold: str
    test_procedure: str
    sprt_alpha: float = 0.05
    sprt_beta: float = 0.10
    sprt_effect_size: float = 0.2
    trivial_flag: bool = False
    # F12 V3: hard-to-vary reasons (Deutsch criterion applied to conditions)
    # Populated by falsify/hard_to_vary.py - empty when condition passes.
    hard_to_vary_reasons: list[str] = Field(default_factory=list)
    registered_at: datetime = Field(default_factory=datetime.utcnow)


class SPRTResult(BaseModel):
    decision: SPRTDecision
    likelihood_ratio: float
    observations_count: int
    alpha: float
    beta: float
    accept_boundary: float
    reject_boundary: float
    stopped_early: bool = False
    claim_text: str = ""  # populated by eif_falsify when a claim_text is available


# ─────────────────────────────────────────────
# 2.4  CausalGateResult - Phase 2.5
# ─────────────────────────────────────────────

CausalVerdict = Literal["PASS", "FAIL", "NEEDS_REVIEW"]
CausalLevel = Literal["ASSOCIATION", "INTERVENTION", "COUNTERFACTUAL"]

# v4 evidence probe verdict - separate from the v3 gate verdict above
CausalEvidenceVerdict = Literal["SUPPORTED", "CONTESTED", "NO_EVIDENCE", "REVERSED"]


class CausalGateResult(BaseModel):
    hypothesis: str
    cause_variable: str
    effect_variable: str
    direction_valid: bool
    confounders_detected: list[str] = Field(default_factory=list)
    causal_level: CausalLevel = "ASSOCIATION"
    intervention_required: bool = False
    disjunctive_bias_flag: bool = False
    verdict: CausalVerdict
    notes: str = ""


class CausalEvidenceResult(BaseModel):
    """Output of CAUSAL_GATE v4 Causal Evidence Probe (CEP).

    Fires only when causal_level >= INTERVENTION and consequence == HIGH.
    Evidence facts are sourced from P3 (DDGS native search) - evidence_source="P3_WEB_SEARCH".
    An LLM is used as a text classifier/parser only (extract_causal_pair + classify_evidence)
    to structure DDGS snippets; it does not supply causal facts from parametric memory.
    If OPENAI_API_KEY is absent, heuristic fallbacks are used and verdict defaults to NO_EVIDENCE.
    """

    claim_text: str
    cause: str
    effect: str
    domain: str
    causal_level: CausalLevel
    search_query: str
    verdict: CausalEvidenceVerdict
    citation: str | None = None
    evidence_summary: str = ""
    evidence_source: Literal["P3_WEB_SEARCH"] = "P3_WEB_SEARCH"
    posterior_delta: float = 0.0
    provenance_flag: str | None = None
    discovered_confounders: list[str] = Field(default_factory=list)
    probed_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# 2.5  CalibrationResult - Phase 3
# ─────────────────────────────────────────────

ConfidenceTier = Literal["HIGH", "MEDIUM", "LOW"]
PriorStrategy = Literal["domain", "empirical_bayes", "max_entropy"]


class CalibrationResult(BaseModel):
    claim_text: str
    prior: float
    likelihood: float
    posterior: float
    ece_score: float | None = None
    conformal_coverage: float | None = None
    confidence_tier: ConfidenceTier
    prior_strategy: PriorStrategy
    calibration_history_size: int = 0
    domain_clamp_applied: bool = False  # F1C3: physics-informed domain ceiling applied
    consequence_of_wrong: RiskLevel = "MEDIUM"  # F13: needed by Extension B for HIGH-only routing

    @property
    def confidence_tier_from_posterior(self) -> ConfidenceTier:
        if self.posterior >= 0.8:
            return "HIGH"
        elif self.posterior >= 0.4:
            return "MEDIUM"
        return "LOW"


class ECEResult(BaseModel):
    """F1: Label-grounded ECE result (arXiv:2501.08292, arXiv:2107.07511).

    label_grounded=True when real binary outcomes drive the computation
    (>= 30 labeled (posterior, outcome) pairs available via outcome_store).
    label_grounded=False when the tier-proxy fallback is used (< 30 labeled pairs).
    sessions_used: count of (posterior, outcome) calibration pairs used in this
    invocation; not a unique MCP session count.
    """

    ece: float | None
    label_grounded: bool = False
    sessions_used: int = 0  # (posterior, outcome) pairs used; not unique MCP session count
    calibration_warning: str | None = None


# ─────────────────────────────────────────────
# 2.6  ChallengeResult - Phase 4
# ─────────────────────────────────────────────

CriticIndependence = Literal[
    "DIFFERENT_FAMILY",
    "DIFFERENT_INFERENCE",
    "DIFFERENT_OBJECTIVE",
    "NONE",
]
ChallengeVerdict = Literal["SURVIVES", "DEFEATED", "NEEDS_REVISION"]


class ChallengeResult(BaseModel):
    claim_text: str
    critic_model: str | None = None
    critic_independence: CriticIndependence = "NONE"
    counter_evidence_found: bool = False
    counter_evidence: list[str] = Field(default_factory=list)
    competing_hypothesis: str | None = None
    verdict: ChallengeVerdict
    self_evaluation_flag: bool = False
    # SC5: hardening score [0.0–1.0] reflecting how adversarial the challenge was.
    # Protocol-only (no critic ran): 0.4. Derived from critic_independence tier:
    #   NONE → 0.3, SAME_FAMILY → 0.5, DIFFERENT_FAMILY → 0.7, DIFFERENT_OBJECTIVE → 0.9.
    # Multi-critic tournament (run_multi_critic_challenge): 1.0.
    # The sycophancy gate fires WEAK_CHALLENGE_WARN when hardening_score < 0.5.
    hardening_score: float = 0.7


# ─────────────────────────────────────────────
# 2.7  UpdateResult - Phase 5
# ─────────────────────────────────────────────

UpdateRecommendation = Literal[
    "MAINTAIN_COURSE",
    "RETURN_TO_DECLARE",
    "ESCALATE",
]
StoppingReason = Literal[
    "EIG_BELOW_THRESHOLD",
    "SPRT_BOUNDARY",
    "COST_EXCEEDS_VALUE",
]


class UpdateResult(BaseModel):
    hypothesis: str
    prior_posterior: float
    new_evidence: str
    updated_posterior: float
    eig: float
    stopping_rule_triggered: bool = False
    stopping_reason: StoppingReason | None = None
    recommendation: UpdateRecommendation


# ─────────────────────────────────────────────
# 2.8  ExplanationArtifact - Phase 5.5
# ─────────────────────────────────────────────

HardToVaryVerdict = Literal["PASS", "FAIL", "SELF_ASSESSED"]
ReachScope = Literal["LOCAL", "BROADER"]


class ExplanationDetail(BaseModel):
    detail_text: str
    prediction_impact: str


class ExplanationArtifact(BaseModel):
    prior_explanation: str
    disconfirming_evidence: str | None = None
    new_explanation: str
    details: list[ExplanationDetail] = Field(default_factory=list)
    hard_to_vary_verdict: HardToVaryVerdict
    testable_predictions: list[str] = Field(default_factory=list)
    reach: ReachScope = "LOCAL"
    reach_implications: str | None = None
    corroborated: bool = False


# ─────────────────────────────────────────────
# 2.9  ProvenanceRecord - Phase 6
# ─────────────────────────────────────────────

OversightStatus = Literal["ESCALATED", "NOT_NEEDED"]


class ProvenanceRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    decision: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    registry: AssumptionRegistry
    falsification_conditions: list[FalsificationCondition] = Field(default_factory=list)
    sprt_results: list[SPRTResult] = Field(default_factory=list)
    causal_gate: CausalGateResult | None = None
    causal_evidence_result: CausalEvidenceResult | None = None
    causal_unverified: bool = False
    calibration: list[CalibrationResult] = Field(default_factory=list)
    challenge: ChallengeResult | None = None
    updates: list[UpdateResult] = Field(default_factory=list)
    explanation: ExplanationArtifact | None = None
    models_used: list[str] = Field(default_factory=list)
    tools_invoked: list[str] = Field(default_factory=list)
    human_oversight: OversightStatus = "NOT_NEEDED"
    contrary_evidence_considered: bool = False
    # Research Object paradigm (arXiv:2604.11261): inspectable, reproducible,
    # integrity-preserving artifact fingerprint.
    input_fingerprint: str | None = None       # SHA-256 of decision + registry content
    model_config_snapshot: dict[str, str] | None = None  # model names + EIF engine version
    # F1: Label-grounded ECE feedback loop (arXiv:2501.08292)
    # NOTE: These fields are a V2 design artifact. The canonical outcome path is
    # outcome_store.py (OutcomeRecord rows), which persists across process restarts.
    # These fields are retained for schema compatibility but are not written by
    # eif_record_outcome; callers should use outcome_store for ECE grounding.
    outcome_observed: bool | None = None       # None = not yet known; V2 compat only
    outcome_recorded_at: datetime | None = None  # V2 compat only
    # F17: aggregated evidence quality flags from this session's EvidenceResult objects.
    # Non-None metric_quality values from all FALSIFY probes are collected here so
    # compliance reports (S6) can surface degraded-evidence claims without traversing
    # individual FalsificationCondition objects. Values: "DEGRADED_METRIC",
    # "SELF_PREFERENCE_BLOCKED", "PRIVATE_DATA_BLOCKED".
    metric_quality_flags: list[str] = Field(default_factory=list)
    # IG6: InputGuardResult snapshot persisted for full audit trail.
    # Allows downstream reviewers to verify whether adversarial injection was
    # attempted and how it affected the session without re-running detection.
    input_guard: dict | None = None
    # EU AI Act article mapping populated by record/compliance.py::map_compliance
    # during assemble_record. Keyed by article label ("Article 9", "Article 12",
    # "Article 13", "Article 14"); values are human-readable reason lines.
    # Persisted so eif_compliance_report can render without recomputing and
    # downstream consumers (e.g. eif_record callers) can inspect article
    # coverage without a second tool call.
    articles_covered: dict[str, list[str]] = Field(default_factory=dict)

    @staticmethod
    def compute_fingerprint(decision: str, registry: AssumptionRegistry) -> str:
        """Compute a SHA-256 fingerprint of the key inputs to this ProvenanceRecord.

        Covers: decision text + all claim texts + claim types + session_id.
        This allows downstream consumers to verify that a ProvenanceRecord was
        produced from a specific decision/registry pair without re-running the
        full EIF pipeline.
        """
        payload = {
            "session_id": registry.session_id,
            "decision": decision,
            "claims": sorted(
                [
                    {"text": c.text, "type": c.claim_type}
                    for c in (registry.known + registry.assumed + registry.guessed)
                ],
                key=lambda x: x["text"],
            ),
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()


# ─────────────────────────────────────────────
# 2.9b  HypothesisAgenda - before FALSIFY
# ─────────────────────────────────────────────


class HypothesisAgendaItem(BaseModel):
    """Single ranked hypothesis with its priority score breakdown."""

    claim_text: str
    claim_type: ClaimType
    consequence_of_wrong: RiskLevel
    current_posterior: float
    eig_score: float
    consequence_weight: float
    boundary_factor: float
    uncertainty_factor: float
    priority_score: float
    nearest_threshold: float
    priority_rank: int
    rationale: str
    fdr_alpha_adjusted: float | None = None       # BH-adjusted significance threshold
    fdr_inflation_risk: str | None = None         # LOW / MEDIUM / HIGH


class HypothesisAgenda(BaseModel):
    """Ranked agenda of hypotheses to test - output of HYPOTHESIS_AGENDA phase."""

    session_id: str
    total_claims: int
    items: list[HypothesisAgendaItem] = Field(default_factory=list)
    deferred: list[HypothesisAgendaItem] = Field(default_factory=list)
    top_recommendation: str
    rationale: str
    max_probes: int | None = None
    fdr_warning: str | None = None               # surfaced when N > 5 (BH 1995)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# 2.10  Programme signals - Phase 8
# ─────────────────────────────────────────────

ProgrammeStatus = Literal["PROGRESSIVE", "STABLE", "DEGENERATIVE"]


class ProgrammeSignals(BaseModel):
    novel_prediction_rate: float = 0.0
    confirmed_prediction_rate: float = 0.0
    patch_rate: float = 0.0
    oscillation_count: int = 0
    status: ProgrammeStatus = "STABLE"


# ─────────────────────────────────────────────
# 2.11  SessionState - the MCP server's runtime unit
# ─────────────────────────────────────────────


class SessionState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    linked_session_id: str | None = None    # optional correlation id for external session tracking
    created_at: datetime = Field(default_factory=datetime.utcnow)
    provenance_chain: list[ProvenanceRecord] = Field(default_factory=list)
    calibration_history: list[CalibrationResult] = Field(default_factory=list)
    programme: ProgrammeSignals = Field(default_factory=ProgrammeSignals)
    paradigm_alerts: list[ParadigmRevisionAlert] = Field(default_factory=list)
    active: bool = True  # Reserved for future session lifecycle management (not currently read/written by tools)
    # F17: aggregated metric_quality flags from the most recent FALSIFY pass.
    # Set by eif_verify; read by eif_record to populate ProvenanceRecord.metric_quality_flags.
    metric_quality_flags: list[str] = Field(default_factory=list)
    # IG6: last InputGuardResult captured for this session.
    # Stored by eif_input_guard; consumed by eif_record → assemble_record.
    last_input_guard: dict | None = None
    # CG4: CEP results keyed by claim_text (hypothesis).
    # Stored by eif_causal_gate; consumed by eif_calibrate to apply posterior_delta.
    cep_results: dict[str, dict] = Field(default_factory=dict)
    # UPDATE history for the granular pipeline (eif_update stores here; eif_record,
    # eif_programme_health, and strategy memory read from here).
    updates: list[UpdateResult] = Field(default_factory=list)
    # Last ChallengeResult from eif_challenge - stored so eif_record can pass it
    # into assemble_record for C9 (contrary_evidence_considered) wiring.
    last_challenge: dict | None = None
    # R5-02: Last AssumptionRegistry from eif_declare or eif_verify - persisted so
    # eif_record always gets a populated registry instead of the empty fallback.
    last_registry: dict | None = None
    # R5-03: Granular pipeline artifacts accumulated across phase tool calls.
    # eif_falsify appends here; eif_record passes the full list to assemble_record.
    last_falsification_conditions: list[dict] = Field(default_factory=list)
    last_sprt_results: list[dict] = Field(default_factory=list)
    # CausalGateResult from eif_causal_gate (distinct from cep_results which holds CEP only).
    last_causal_gate: dict | None = None
    # ExplanationArtifact from eif_explain.
    last_explanation: dict | None = None


# ─────────────────────────────────────────────
# 2.12  ParadigmRevisionAlert - PIEVO-inspired
# ─────────────────────────────────────────────

class ParadigmRevisionAlert(BaseModel):
    """Alert for systematic unidirectional posterior drift across UPDATE iterations.

    Fired when PARADIGM_ALERT_THRESHOLD or more consecutive updates all push
    the posterior in the same direction with mean shift >= PARADIGM_MIN_AVG_SHIFT.
    Surfaces in eif_programme_health. Does not auto-revise; raises for human review.

    Research: PIEVO (arXiv:2602.06448, 2026); Kuhn (1962) paradigm shifts.
    """

    session_id: str
    direction: Literal["DOWN", "UP", "MIXED"]
    consecutive_updates: int
    avg_posterior_shift: float
    affected_claims: list[str] = Field(default_factory=list)
    recommendation: str
    detected_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# V2 schemas
# ─────────────────────────────────────────────

# ── F2: IRIS Full Causal Discovery (arXiv:2510.09217, ACL 2025) ────────────

PearlLevel = Literal["ASSOCIATION", "INTERVENTION", "COUNTERFACTUAL"]


class CausalEdge(BaseModel):
    """Single edge in the causal graph produced by the IRIS pipeline."""

    cause: str
    effect: str
    level: PearlLevel = "ASSOCIATION"
    evidence_count: int = 0
    confidence: float = 0.0


class CausalGraph(BaseModel):
    """Output of IRIS full iterative causal discovery pipeline.

    Research: IRIS arXiv:2510.09217 (ACL 2025).
    """

    cause: str
    effect: str
    domain: str
    edges: list[CausalEdge] = Field(default_factory=list)
    missing_variables: list[str] = Field(default_factory=list)
    iterations_run: int = 0
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    documents_retrieved: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── F3: PIEVO Principle Revision (arXiv:2602.06448) ───────────────────────

class PrincipleRevisionProposal(BaseModel):
    """Proposal for a principle-level revision of the session's framework.

    PROPOSED not APPLIED - requires human confirmation via eif_approve_revision.
    Research: PIEVO arXiv:2602.06448; Kuhn (1962) paradigm shifts.
    Constraint F3C3: confidence must never exceed 0.80 (Deutsch fallibilism).
    """

    session_id: str
    affected_principle: str
    revision_direction: str
    supporting_evidence: list[str] = Field(default_factory=list)
    confidence: float  # F3C3: must be <= 0.80
    alternative_hypotheses: list[str] = Field(default_factory=list)  # F3C1: >= 2
    requires_confirmation: bool = True  # F3C2: always True
    triggered_by_alert_direction: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── F4: Research Object + DeepTRACE (arXiv:2604.11261, arXiv:2509.04499) ──

class DeepTRACEAudit(BaseModel):
    """8-dimension audit framework from DeepTRACE (arXiv:2509.04499).

    Each dimension score is in [0, 1]. overall_score = mean of all 8.
    Dimensions below 0.5 generate provenance_flags.
    """

    answer_accuracy: float = 0.0
    source_accuracy: float = 0.0
    citation_accuracy: float = 0.0
    claim_evidence_alignment: float = 0.0
    reasoning_transparency: float = 0.0
    uncertainty_disclosure: float = 0.0
    coverage_completeness: float = 0.0
    temporal_currency: float = 0.0

    @property
    def overall_score(self) -> float:
        dims = [
            self.answer_accuracy, self.source_accuracy, self.citation_accuracy,
            self.claim_evidence_alignment, self.reasoning_transparency,
            self.uncertainty_disclosure, self.coverage_completeness, self.temporal_currency,
        ]
        return round(sum(dims) / len(dims), 4)

    @property
    def dim_scores(self) -> dict[str, float]:
        return {
            "answer_accuracy": self.answer_accuracy,
            "source_accuracy": self.source_accuracy,
            "citation_accuracy": self.citation_accuracy,
            "claim_evidence_alignment": self.claim_evidence_alignment,
            "reasoning_transparency": self.reasoning_transparency,
            "uncertainty_disclosure": self.uncertainty_disclosure,
            "coverage_completeness": self.coverage_completeness,
            "temporal_currency": self.temporal_currency,
        }


class ResearchObject(BaseModel):
    """Research Object paradigm (arXiv:2604.11261) for full provenance capture.

    Structured { inputs, process, outputs, provenance } with DeepTRACE audit.
    """

    session_id: str
    decision: str
    verdict: str  # ACT / HALT / REVISE
    dimensions: DeepTRACEAudit
    provenance_flags: list[str] = Field(default_factory=list)
    total_claims: int = 0
    phases_run: list[str] = Field(default_factory=list)
    models_used: list[str] = Field(default_factory=list)
    tools_invoked: list[str] = Field(default_factory=list)
    contrary_evidence_included: bool = False
    uncertain_claims: list[str] = Field(default_factory=list)
    stale_sources: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── F5: ISC AI Disclosure Taxonomy ────────────────────────────────────────

ISCActivityType = Literal[
    "hypothesis_generation", "data_collection", "analysis",
    "peer_review", "documentation", "human_review", "human_required",
]


class ISCDisclosureEntry(BaseModel):
    """Single entry in the ISC AI disclosure taxonomy.

    Source: ISC Global Reporting Standard for AI in Research (2026 draft).
    https://council.science/our-work/ai-disclosure-in-research/
    """

    eif_phase: str
    isc_type: ISCActivityType
    model_name: str
    task_description: str
    human_review_step: str | None = None
    isc_draft_compliance: bool = True  # F5 is ISC_DRAFT_COMPLIANCE until standard finalizes


class ISCDisclosure(BaseModel):
    """Complete ISC disclosure for an EIF session.

    Status: ISC_DRAFT_COMPLIANCE - standard finalizing 2026-2027.
    """

    session_id: str
    entries: list[ISCDisclosureEntry] = Field(default_factory=list)
    isc_version: str = "draft-2026"
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ── F8: DASES Adversarial Replicator (arXiv:2603.29045) ───────────────────

class ReplicationResult(BaseModel):
    """Result of adversarial replication via DASES-style falsifier.

    Research: DASES (Abyss Falsifier) arXiv:2603.29045 (2026).
    F8C1: system_prompt must not contain 'evaluate'; must contain 'fail'/'falsif'.
    F8C2: test_designed must be non-empty, != claim verbatim, len >= 50.
    """

    claim_text: str
    survived: bool
    test_designed: str
    test_result: str
    confidence: float = 0.0
    replication_mode: str = "DASES"
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# V3 schemas
# ─────────────────────────────────────────────

# ── F11: Session Outcome Feedback Loop ───────────────────────────────────────

class OutcomeRecord(BaseModel):
    """Single labeled session outcome - persisted to ~/.eif/outcome_store.json.

    Provides the ground-truth signal needed for label-grounded ECE (F1C1)
    and empirical Bayes prior (Architecture §5.4 Strategy 2).

    Research: arXiv:2501.08292 (label-grounded ECE); Architecture §5.4.
    """

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    provenance_record_id: str
    outcome: bool               # True = agent was correct; False = was wrong
    domain: str | None = None   # optional domain tag for domain-specific ECE
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


# ── F13: Independent Replication (Extension B) ───────────────────────────────

IndependentReplicationAgreement = Literal["CONVERGENT", "DIVERGENT"]


class IndependentReplicationResult(BaseModel):
    """Result of convergent independent replication (Extension B).

    Distinct from DASES adversarial replication (F8/ReplicationResult).
    This asks: given the same evidence, does an independent derivation
    starting from flat prior (P(H)=0.5) reach the same routing verdict?

    Divergence = prior-dependent conclusion → human review required.
    Research: Architecture §Extension B; multi_agent_review.md.
    """

    session_id: str
    provenance_record_id: str
    original_routing: str              # ACT / REVISE / HALT
    independent_routing: str           # derived from flat prior
    original_min_posterior: float
    independent_min_posterior: float
    prior_sensitivity: float           # |original - independent| min posterior delta
    agreement_type: IndependentReplicationAgreement
    diverged: bool
    human_review_required: bool
    claims_compared: int = 0
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── F14: Catch Rate Measurement ───────────────────────────────────────────────

class CatchRateReport(BaseModel):
    """Empirical catch rate measurement for the compound error model.

    Literature defaults (f=0.6, u=0.5, c=0.4) from Architecture §9.2.
    Empirical rates measured from outcome-linked provenance records (OutcomeRecord rows).

    Research: Architecture §9.2 Compound Error Model; §5.1 Cross-Check gaps.
    """

    # Empirical measurements (0.0 when denominator is zero - intent F14C1)
    f_empirical: float = 0.0           # FALSIFY catch rate
    c_empirical: float | None = None   # CHALLENGE catch rate
    u_empirical: float | None = None   # UPDATE routing-change rate
    sessions_measured: int = 0         # count of outcome-linked provenance records (not unique session IDs)
    data_status: str = "INSUFFICIENT_DATA"  # INSUFFICIENT_DATA | PARTIAL | SUFFICIENT

    # Literature defaults for comparison (Architecture §9.2: f=0.6, c=0.4, u=0.5)
    f_literature: float = 0.6
    c_literature: float = 0.4   # CHALLENGE literature baseline
    u_literature: float = 0.5   # UPDATE literature baseline

    # Compound error residuals
    compound_error_empirical: float | None = None
    compound_error_literature: float | None = None

    # Which rates are used for the primary compound calculation
    f_used: float = 0.6
    c_used: float = 0.4
    u_used: float = 0.5

    generated_at: datetime = Field(default_factory=datetime.utcnow)


SessionState.model_rebuild()

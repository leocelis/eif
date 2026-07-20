"""EIF MCP server - built on FastMCP.

Exposes all 25 EIF tools and 5 resources:

  Session tool:
    eif_new_session

  Core pipeline tools (granular):
    eif_get_context, eif_declare, eif_falsify, eif_causal_gate,
    eif_calibrate, eif_challenge, eif_update, eif_explain,
    eif_record, eif_replicate, eif_programme_health,
    eif_provenance, eif_check_rules_installed

  V2/V3 extension tools:
    eif_sycophancy_gate, eif_input_guard, eif_hypothesis_agenda

  Facade tools (one-call pipeline):
    eif_extract_claims_from_decision, eif_verify, eif_demo, eif_get_session

  Observability and compliance tools:
    eif_compliance_report, eif_record_outcome,
    eif_calibration_report, eif_catch_rate_report

  Resources (read-only context):
    eif://session/{id}/summary
    eif://session/{id}/registry
    eif://session/{id}/provenance
    eif://session/{id}/programme
    eif://session/{id}/calibration

Cursor integration (.cursor/mcp.json):
    {
      "mcpServers": {
        "eif": {
          "command": "/path/to/venv/bin/python",
          "args": ["-m", "eif.mcp_server.server"],
          "env": {}
        }
      }
    }
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import UTC, datetime

from eif import ENGINE_VERSION
from eif import session as session_store
from eif.schemas import (
    CONFORMAL_MIN_HISTORY,
    EIG_THRESHOLD,
    PRIOR_EMPIRICAL_MIN,
    THRESHOLD_ACT,
    THRESHOLD_HALT,
    THRESHOLD_REVISE,
    CalibrationResult,
    ClaimInput,
)

# ── Structured log ────────────────────────────────────────────────────────────

_LOG_PATH = os.environ.get("EIF_LOG_PATH", os.path.expanduser("~/.eif/eif_mcp.log"))
_handlers: list[logging.Handler] = []
if os.environ.get("EIF_ENV") == "production":
    _handlers.append(logging.StreamHandler())
else:
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        _handlers.append(logging.FileHandler(_LOG_PATH, mode="a"))
    except OSError:
        _handlers.append(logging.StreamHandler())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=_handlers,
)
_log = logging.getLogger("eif.mcp")

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise ImportError(
        "MCP support requires: pip install 'eif-engine[mcp]'"
    ) from exc

# ── Server-level instructions ─────────────────────────────────────────────────

SERVER_INSTRUCTIONS = """
EIF - Runtime gate for AI agent claims.

FIRST-USE FLOW (three-tool path, in order):
  1. eif_new_session - call ONCE per distinct decision or task, store the
     returned session_id. Every other tool requires it. Do not call it
     per claim - one session tracks the whole decision chain.
  2. eif_extract_claims_from_decision - CALL THIS when the user describes
     a decision their agent is about to make in plain text. Ask: "What
     decision is your agent about to make?" Then pass their answer here.
     Returns 2-4 structured claims ranked by HALT probability. Skip this
     step only if the user has already written structured claims.
  3. eif_verify(session_id=...) - pass the session_id from step 1 and the
     claims from step 2. Returns PASS or HALT with evidence and a dollar
     cost figure.

WHEN TO CALL eif_extract_claims_from_decision:
  - Any time the user describes an agent output or decision in natural language.
  - The user has NOT written structured claim JSON yet.
  - The user says things like: "my agent says...", "it decided...",
    "the brief states...", "the recommendation was..."

WHEN TO CALL eif_verify:
  - After eif_extract_claims_from_decision has returned structured claims.
  - When the user already has structured claims (skipping extraction).
  - Before any output with statistics, cost figures, compliance requirements,
    causal claims, or API behavior stated with high confidence.
  - After multi-turn exchanges where the user pushed back - sycophantic
    drift (position change without new evidence) is invisible otherwise.

WHAT eif_verify CATCHES THAT NAIVE CHECKS MISS:
  1. Sycophantic drift - model changed answer under social pressure, not evidence.
  2. Self-preference bias - model prefers its own generated claims 67-82% of the
     time (arXiv:2509.00462). P4 self-validation is blocked for self-generated claims.
  3. Causal errors - model presents a correlation as causation.
  4. Instability (stochastic fabrication) - calling the same claim twice returns
     different numbers. instability_signals in the response flags this. If you see
     it, the model is not drawing from a stable factual source.

OUTBOUND CALLS (what leaves your machine):
  Verification logic runs on your server. Depending on tiers and keys:
  • P3 (web search): DDGS read-only queries - claim-derived search terms egress.
  • P4 (parametric probes): not fired by eif_verify (no LLM probe is wired there).
  • OpenAI API egress happens only in eif_challenge (multi-critic) and the causal
    evidence probe, and only if OPENAI_API_KEY is set.
  • CEP (Causal Evidence Probe): OpenAI + DDGS when OPENAI_API_KEY set and claim is
    HIGH-consequence INTERVENTION/COUNTERFACTUAL.
  Raw claim payloads, LLM responses, and API keys are NOT sent to any scoring service.
  Evidence queries use claim-derived terms only. Call once per claim set.

ADVANCED USE (granular pipeline - only when you need step-level visibility):
  eif_input_guard → eif_declare → eif_falsify → eif_causal_gate → eif_calibrate →
  eif_challenge → eif_sycophancy_gate → eif_update → eif_explain → eif_record
  eif_input_guard runs before eif_declare; eif_sycophancy_gate runs after eif_challenge.
  Optional: eif_hypothesis_agenda (before eif_falsify for multi-claim ordering),
            eif_replicate (after eif_record to structure replication protocol),
            eif_programme_health (after ≥ 3 records for Lakatos health assessment).

RESOURCES (read-only session state - five URIs):
  eif://session/{id}/summary      - compact session overview
  eif://session/{id}/registry     - latest AssumptionRegistry (or last_registry fallback)
  eif://session/{id}/provenance   - full provenance chain for compliance
  eif://session/{id}/programme    - Lakatos programme signals (novel/confirmed/patch rates)
  eif://session/{id}/calibration  - calibration history for ECE computation

DECISION THRESHOLDS (THRESHOLD_ACT=0.70, THRESHOLD_REVISE=0.40, THRESHOLD_HALT=0.20):
  posterior >= 0.70 → MAINTAIN_COURSE (ACT)
  posterior 0.40–0.70 → RETURN_TO_DECLARE / REVISE (gather more evidence)
  posterior 0.20–0.40 → REVISE with urgency (high uncertainty)
  posterior < 0.20 → HALT (escalate to human)
""".strip()

# ── FastMCP app ───────────────────────────────────────────────────────────────

def _transport_security():
    """Transport security for the HTTP/SSE transports.

    Local dev (default): keep FastMCP's default localhost-only DNS rebinding
    protection. Hosted behind a custom domain, the incoming Host header is that
    domain, which the default policy rejects ("Invalid Host header"). In
    production the Bearer-key auth middleware is the access control, so DNS
    rebinding protection is disabled unless EIF_ALLOWED_HOSTS pins a host list.
    """
    if os.environ.get("EIF_ENV") != "production":
        return None
    try:
        from mcp.server.sse import TransportSecuritySettings
    except ImportError:
        return None
    raw = os.environ.get("EIF_ALLOWED_HOSTS", "").strip()
    if raw:
        hosts = [h.strip() for h in raw.split(",") if h.strip()]
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
        )
    return TransportSecuritySettings(enable_dns_rebinding_protection=False)


_fastmcp_kwargs: dict = {"instructions": SERVER_INSTRUCTIONS}
_ts = _transport_security()
if _ts is not None:
    _fastmcp_kwargs["transport_security"] = _ts

mcp = FastMCP("eif-engine", **_fastmcp_kwargs)

# ── EIF context reference card ────────────────────────────────────────────────

_EIF_PHASES = [
    # Optional pre-pipeline guards (run before DECLARE in the granular path)
    {"id": "INPUT_GUARD", "description": "Detect adversarial manipulation patterns (IG1–IG7) before processing the decision", "trigger": "Optionally before DECLARE when prompt injection or adversarial framing is suspected", "output": "InputGuardSnapshot"},
    # Core pipeline phases
    {"id": "DECLARE", "description": "Name and classify every assumption (KNOWN/ASSUMED/GUESSED)", "trigger": "Before any decision with load-bearing assumptions", "output": "AssumptionRegistry"},
    {"id": "FALSIFY", "description": "Define what observation would prove each assumption wrong; run SPRT", "trigger": "After DECLARE, for each ASSUMED/GUESSED claim", "output": "FalsificationCondition + SPRTResult"},
    {"id": "CAUSAL_GATE", "description": "Check Pearl causal level; detect confounders and disjunctive bias", "trigger": "When the hypothesis describes a causal relationship", "output": "CausalGateResult"},
    {"id": "CALIBRATE", "description": "Compute Bayesian posterior with ECE and conformal coverage", "trigger": "After FALSIFY, once you have evidence", "output": "CalibrationResult"},
    {"id": "CHALLENGE", "description": "Adversarially probe with an independent critic", "trigger": "When posterior is uncertain (0.4-0.7) or HIGH stakes", "output": "ChallengeResult"},
    # Post-CHALLENGE gates (must run between CHALLENGE and UPDATE in the granular path)
    {"id": "SYCOPHANCY_GATE", "description": "Detect agreement-before-evidence, position drift, and sycophantic patterns (M1–M4)", "trigger": "After CHALLENGE, before UPDATE - when model agreement with user pressure is a concern", "output": "SycophancyResult"},
    {"id": "UPDATE", "description": "Sequential Bayes update; compute EIG; apply stopping rules", "trigger": "After CHALLENGE (+ SYCOPHANCY_GATE if used) with new evidence", "output": "UpdateResult"},
    {"id": "EXPLAIN", "description": "Hard-to-vary check on the mechanism; extract testable predictions", "trigger": "After UPDATE when posterior is stable", "output": "ExplanationArtifact"},
    {"id": "RECORD", "description": "Store provenance record; map to EU AI Act compliance", "trigger": "Always - after completing the loop for a decision", "output": "ProvenanceRecord"},
    {"id": "REPLICATE", "description": "Structure a replication protocol; evaluate agreement", "trigger": "When the claim is important and can be replicated", "output": "Replication verdict"},
    {"id": "PROGRAMME_HEALTH", "description": "Assess Lakatos programme health (PROGRESSIVE/STABLE/DEGENERATIVE)", "trigger": "After >= 3 ProvenanceRecords exist", "output": "ProgrammeSignals"},
]

_EIF_RULES = [
    {"id": "Rule 0", "summary": "Tiered activation: LOW stakes=silent, MEDIUM=inline markers, HIGH=Assumption Check Card + Understanding block"},
    {"id": "Rule 1", "summary": "DECLARE: classify all claims as KNOWN/ASSUMED/GUESSED before acting"},
    {"id": "Rule 2", "summary": "CALIBRATE: mark every load-bearing claim with ✓/~/? confidence markers"},
    {"id": "Rule 5", "summary": "VERIFY (host-agent guidance only - not enforced by MCP): emit Verification Beat before irreversible actions (file writes, shell commands, git ops, deletions)"},
    {"id": "Rule 10", "summary": "FOLK THEORY: name and correct wrong assumptions before responding"},
    {"id": "Rule 14", "summary": "ANTHROPOMORPHISM CEILING: declare AI identity factually; no companionship framing"},
]


# ─────────────────────────────────────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool(
    name="eif_new_session",
    description=(
        "Initialize a new EIF session. Call ONCE per distinct decision or task and store "
        "the returned session_id - it is required by every other EIF tool (eif_verify, "
        "eif_declare, eif_falsify, eif_get_session, ...). Do NOT call it once per claim; "
        "one session tracks the full DECLARE -> ... -> RECORD chain for a decision. "
        "To start tracking a new, unrelated decision, call eif_new_session again and "
        "discard the old session_id. "
        "Parameters: linked_session_id (optional - links this session to a prior one, "
        "e.g. when a decision revisits an earlier HALT). "
        "Returns: session_id (str)."
    ),
)
async def eif_new_session(linked_session_id: str | None = None) -> dict:
    """Create a new EIF session. Returns {session_id: str}."""
    sess = await session_store.new_session(linked_session_id=linked_session_id)
    _log.info(
        "TOOL  eif_new_session  session=%s  linked=%s",
        sess.session_id[:8], linked_session_id[:8] if linked_session_id else None,
    )
    return {"session_id": sess.session_id}


@mcp.tool(
    name="eif_get_context",
    description=(
        "ADVANCED: Load EIF phase descriptions, decision thresholds, and the quick reference card. "
        "Call once at the start of a session when using the granular pipeline (eif_declare → eif_falsify → ...). "
        "Not needed when using eif_verify - eif_verify is an integrated façade (evidence collection + "
        "sycophancy/instability gates + calibration summary) that does not invoke every granular tool. "
        "Parameters: topic (optional string - filters phases and rules to entries whose id or description "
        "contains the topic substring; omit to return all). "
        "Returns: phases[] (each: {id, description, trigger, output}), "
        "rules[] (each: {id, summary}), "
        "quick_reference (single synthesized string with thresholds, EIG stop, and pipeline loop summary)."
    ),
)
def eif_get_context(topic: str | None = None) -> dict:
    """Return EIF reference card. topic filters to a specific phase/rule."""
    phases = _EIF_PHASES
    rules = _EIF_RULES

    if topic:
        topic_upper = topic.upper()
        phases = [p for p in phases if topic_upper in p["id"].upper() or topic_upper in p["description"].upper()]
        rules = [r for r in rules if topic_upper in r["id"].upper() or topic_upper in r["summary"].upper()]

    quick_reference = (
        f"EIF Engine v{ENGINE_VERSION} - Quick Reference\n"
        "Core loop: DECLARE → FALSIFY → CAUSAL_GATE → CALIBRATE → CHALLENGE → SYCOPHANCY_GATE → UPDATE → EXPLAIN → RECORD\n"
        "Optional guards: INPUT_GUARD (before DECLARE) | SYCOPHANCY_GATE (after CHALLENGE, before UPDATE)\n"
        f"Thresholds: ACT={THRESHOLD_ACT}, REVISE={THRESHOLD_REVISE}, HALT={THRESHOLD_HALT}\n"
        f"EIG stop: < {EIG_THRESHOLD} nats | Conformal history: {CONFORMAL_MIN_HISTORY} | Empirical prior: {PRIOR_EMPIRICAL_MIN}\n"
        "H₀ = claim-IS-TRUE (POPPER orientation) | REJECT H₀ = claim falsified"
    )

    _log.info("TOOL  eif_get_context  topic=%s", topic)
    return {"phases": phases, "rules": rules, "quick_reference": quick_reference}


@mcp.tool(
    name="eif_declare",
    description=(
        "ADVANCED: Classify every claim in a decision as KNOWN (externally verified), "
        "ASSUMED (plausible but unverified), or GUESSED (no evidence basis). "
        "Call this first in the granular pipeline, before eif_falsify. "
        "Use eif_verify instead if you want the full pipeline in one call. "
        "Parameters: session_id, decision (the agent's claim or recommendation text), "
        "claims[] (list of ClaimInput dicts - each with text, claim_type, "
        "consequence_of_wrong, optionally evidence_source/falsification_condition/claim_mode). "
        "Flags HARKing (hypothesis stated as prediction after results are known). "
        "Set claim_mode='EXPLORATORY' or 'CONFIRMATORY' on each claim to enable "
        "inferential correctness checks (F9). Returns exploration_warning when every claim's "
        "claim_mode is 'EXPLORATORY' (registry modes == {EXPLORATORY}); no routing check is applied. "
        "Returns: registry with known[], assumed[], guessed[], "
        "high_risk_claims[] (ASSUMED or GUESSED claims with HIGH consequence - registry.high_risk_assumed), "
        "harking_detected, falsification_required[], stale_evidence_warnings[], exploration_warning. "
        "Note: C13 HARKing trigger 3 (fc.registered_at > claim.verified_at) fires only during "
        "eif_record/assemble_record when both falsification conditions and claims are assembled together; "
        "harking_detected here reflects triggers 1 and 2 only (post-hoc FC detection from claim text)."
    ),
)
async def eif_declare(
    session_id: str,
    decision: str,
    claims: list[dict],
) -> dict:
    """Phase 1: DECLARE - name and classify every assumption."""
    from eif.declare.harking_guard import detect_harking
    from eif.declare.registry import build_registry

    if not decision:
        raise ValueError("decision string cannot be empty")

    claim_objects = [ClaimInput.model_validate(c) for c in claims]
    registry, stale_warnings = build_registry(session_id, decision, claim_objects)
    registry = detect_harking(registry)

    # R5-02: persist registry so eif_record can reconstruct a populated AssumptionRegistry
    # instead of falling back to an empty one when the granular pipeline is used.
    await session_store.update_session(session_id, last_registry=registry.model_dump())

    falsification_required = [
        c.text for c in (registry.assumed + registry.guessed)
        if not c.falsification_condition
    ]

    _log.info(
        "TOOL  eif_declare  session=%s  decision=%r  known=%d  assumed=%d  guessed=%d  harking=%s",
        session_id[:8], decision[:40], len(registry.known), len(registry.assumed),
        len(registry.guessed), registry.harking_flag,
    )

    exploration_warning = next(
        (w for w in stale_warnings if w.startswith("EXPLORATION_ONLY:")), None
    )
    clean_stale = [w for w in stale_warnings if not w.startswith("EXPLORATION_ONLY:")]

    return {
        "registry": registry.model_dump(),
        "harking_detected": registry.harking_flag,
        "high_risk_claims": [c.model_dump() for c in registry.high_risk_assumed],
        "falsification_required": falsification_required,
        "stale_evidence_warnings": clean_stale,
        "exploration_warning": exploration_warning,
    }


@mcp.tool(
    name="eif_falsify",
    description=(
        "ADVANCED: Define what observation would prove a claim wrong, then optionally run SPRT "
        "(Sequential Probability Ratio Test) against provided observations. "
        "Call after eif_declare for each ASSUMED or GUESSED claim. "
        "Use eif_verify instead if you want the full pipeline in one call. "
        "Parameters: session_id, claim_text, condition (the falsification statement), "
        "threshold (e.g. 'p<0.05'), test_procedure (e.g. 'web_search'), "
        "observations[] (list of bool - True=supports claim, False=refutes; optional), "
        "alpha (default 0.05), beta (default 0.10), effect_size (default 0.20). "
        "Flags trivial falsification conditions (unfalsifiable claims) and hard-to-vary "
        "conditions (F12): conditions with qualitative-only thresholds, no named test "
        "procedure, or adjustable language are flagged with hard_to_vary_reasons[] explaining why. "
        "Returns: condition (full FalsificationCondition schema including claim_text, condition, "
        "threshold, test_procedure, trivial_flag, hard_to_vary_reasons[], sprt_alpha, sprt_beta, "
        "sprt_effect_size, registered_at), "
        "trivial_flag (top-level convenience copy of condition.trivial_flag), "
        "sprt_result (when observations provided - full SPRTResult schema: decision (ACCEPT/REJECT/CONTINUE), "
        "likelihood_ratio, observations_count, alpha, beta, accept_boundary, reject_boundary, "
        "stopped_early, claim_text)."
    ),
)
async def eif_falsify(
    session_id: str,
    claim_text: str,
    condition: str,
    threshold: str,
    test_procedure: str,
    observations: list[bool] | None = None,
    alpha: float = 0.05,
    beta: float = 0.10,
    effect_size: float = 0.2,
) -> dict:
    """Phase 2: FALSIFY - define and test falsification conditions."""
    from eif.falsify.condition import build_condition
    from eif.falsify.sprt import run_sprt

    fc = build_condition(claim_text, condition, threshold, test_procedure, alpha, beta, effect_size)

    sprt_result = None
    if observations is not None:
        sprt_result = run_sprt(fc, observations)

    _log.info(
        "TOOL  eif_falsify  session=%s  claim=%r  trivial=%s  sprt=%s",
        session_id[:8], claim_text[:40], fc.trivial_flag,
        sprt_result.decision if sprt_result else "not_run",
    )

    # R5-03: accumulate per-claim falsification artifacts in session so eif_record
    # can pass them to assemble_record (immutable audit trail).
    try:
        _falsify_sess = await session_store.get_session(session_id)
        _new_fcs = list(_falsify_sess.last_falsification_conditions) + [fc.model_dump()]
        _new_sprt = list(_falsify_sess.last_sprt_results)
        if sprt_result is not None:
            _new_sprt.append(sprt_result.model_dump())
        await session_store.update_session(
            session_id,
            last_falsification_conditions=_new_fcs,
            last_sprt_results=_new_sprt,
        )
    except Exception as _fs_exc:  # noqa: BLE001
        _log.warning("eif_falsify: session persist failed (non-fatal): %s", _fs_exc)

    return {
        "condition": fc.model_dump(),
        "trivial_flag": fc.trivial_flag,
        "sprt_result": sprt_result.model_dump() if sprt_result else None,
    }


@mcp.tool(
    name="eif_causal_gate",
    description=(
        "ADVANCED: Call this when a claim asserts that A causes B - not merely correlates. "
        "Catches the most dangerous claim type: correlation presented as causation. "
        "Parameters: session_id, hypothesis (causal claim text), cause_variable, effect_variable, "
        "consequence ('LOW'/'MEDIUM'/'HIGH' - default MEDIUM; HIGH triggers CEP search), "
        "potential_confounders[] (optional list of known confounders), "
        "iris_full_pipeline (bool - run full IRIS confounder discovery; default False), "
        "claim_text (optional - must match the text used in eif_calibrate so CEP posterior_delta is applied). "
        "Note: causal_level (ASSOCIATION/INTERVENTION/COUNTERFACTUAL) is an output field derived from evidence, "
        "not a caller-supplied parameter. "
        "Detects undocumented confounders, validates causal level (ASSOCIATION/INTERVENTION/COUNTERFACTUAL), "
        "flags disjunctive bias (AND-hypothesis tested with observational evidence only), "
        "and runs IRIS-inspired active confounder discovery (surfaces unknown-unknown confounders). "
        "For HIGH-consequence claims at INTERVENTION or COUNTERFACTUAL level, also runs the "
        "Causal Evidence Probe (CEP v4): targeted P3 evidence search for independent causal "
        "studies (RCTs, meta-analyses, natural experiments). CEP result includes verdict "
        "(SUPPORTED/CONTESTED/NO_EVIDENCE/REVERSED), citation, posterior_delta, and "
        "provenance_flag (CAUSAL_UNVERIFIED when no evidence found on HIGH claims, per EU AI Act Art.9). "
        "Requires OPENAI_API_KEY for CEP (skipped gracefully if absent). "
        "Pass claim_text matching the text you will use in eif_calibrate so the CEP "
        "posterior_delta (CG4) is applied automatically during calibration. "
        "Returns: verdict (PASS/FAIL/NEEDS_REVIEW), confounders_detected[], discovered_confounders[], "
        "causal_level, intervention_required, disjunctive_bias_flag, causal_evidence (CEP result or null). "
        "Also includes full CausalGateResult schema fields: hypothesis, cause_variable, effect_variable, "
        "direction_valid, notes, and causal_graph (CausalGraph model, present when IRIS pipeline ran)."
    ),
)
async def eif_causal_gate(
    session_id: str,
    hypothesis: str,
    cause_variable: str,
    effect_variable: str,
    consequence: str = "MEDIUM",
    potential_confounders: list[str] | None = None,
    iris_full_pipeline: bool = False,
    claim_text: str | None = None,
) -> dict:
    """Phase 2.5: CAUSAL_GATE - validate causal reasoning.

    V2: set iris_full_pipeline=True to run the IRIS 6-step iterative discovery
    pipeline (F2, arXiv:2510.09217) instead of the single-pass confounder search.
    Adds significant latency (2 web search iterations) but discovers multi-hop
    confounder chains. Result includes causal_graph with edges and missing_variables.
    """
    from eif.causal_gate.confound import check_confounders, discover_confounders
    from eif.causal_gate.direction import check_direction
    from eif.causal_gate.intervention import check_intervention, classify_causal_level
    from eif.schemas import CausalGateResult

    if cause_variable == effect_variable:
        raise ValueError(f"cause_variable and effect_variable cannot be the same: {cause_variable!r}")

    direction_valid = check_direction(cause_variable, effect_variable, hypothesis)
    confounders = check_confounders(hypothesis, potential_confounders)
    causal_level = classify_causal_level(hypothesis)
    intervention_required, disjunctive_bias = check_intervention(hypothesis, causal_level)

    # IRIS active confounder discovery - surfaces unknown-unknown confounders
    # Derive a lightweight domain hint from hypothesis text for the search query
    _hyp_lower = hypothesis.lower()
    if any(w in _hyp_lower for w in ("health", "medical", "clinical", "patient", "drug")):
        _domain_hint = "healthcare"
    elif any(w in _hyp_lower for w in ("financ", "invest", "market", "trade", "risk")):
        _domain_hint = "finance"
    elif any(w in _hyp_lower for w in ("legal", "law", "court", "regulat")):
        _domain_hint = "legal"
    else:
        _domain_hint = ""
    active_confounders = discover_confounders(
        cause=cause_variable,
        effect=effect_variable,
        domain=_domain_hint,
        hypothesis=hypothesis,
    )

    notes_parts = []
    if confounders:
        notes_parts.append(f"Undocumented confounders: {confounders}")
    if active_confounders:
        notes_parts.append(f"Active discovery found potential confounders: {active_confounders}")
    if intervention_required:
        notes_parts.append(f"Hypothesis requires {causal_level} evidence but only ASSOCIATION available")
    if disjunctive_bias:
        notes_parts.append("Disjunctive bias risk: conjunctive 'AND' hypothesis with observational evidence only")

    if confounders or intervention_required:
        verdict = "FAIL"
    elif disjunctive_bias or active_confounders:
        verdict = "NEEDS_REVIEW"
    else:
        verdict = "PASS"

    result = CausalGateResult(
        hypothesis=hypothesis,
        cause_variable=cause_variable,
        effect_variable=effect_variable,
        direction_valid=direction_valid,
        confounders_detected=confounders,
        causal_level=causal_level,
        intervention_required=intervention_required,
        disjunctive_bias_flag=disjunctive_bias,
        verdict=verdict,
        notes=" | ".join(notes_parts),
    )

    # F2: IRIS full pipeline (opt-in, V2)
    causal_graph = None
    if iris_full_pipeline:
        try:
            from eif.causal_gate.iris_pipeline import run as iris_run  # noqa: PLC0415
            causal_graph = iris_run(
                cause=cause_variable,
                effect=effect_variable,
                domain=_domain_hint,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("IRIS full pipeline failed (non-fatal): %s", exc)

    # CAUSAL_GATE v4: Causal Evidence Probe (CG1–CG7)
    # Fires ONLY when consequence=HIGH AND causal_level in INTERVENTION/COUNTERFACTUAL.
    # CG1 is explicit: ASSOCIATION-level claims must bypass the probe entirely.
    # Requires OPENAI_API_KEY; skipped gracefully if absent (CG8).
    # CG5: wrapped with asyncio.wait_for (3 s) to prevent DDGS/OpenAI hangs.
    _CEP_LEVELS = {"INTERVENTION", "COUNTERFACTUAL"}
    cep_result = None
    import os as _os
    if _os.environ.get("OPENAI_API_KEY") and consequence == "HIGH" and causal_level in _CEP_LEVELS:
        try:
            import openai as _openai  # noqa: PLC0415

            from eif.causal_gate.evidence_probe import run_causal_evidence_probe  # noqa: PLC0415

            _client = _openai.OpenAI(api_key=_os.environ["OPENAI_API_KEY"])

            def _llm_fn(prompt: str) -> str:  # lightweight, no caching
                resp = _client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    timeout=30,
                )
                return resp.choices[0].message.content or ""

            # CG5: run synchronous CEP in a thread with a 3 s asyncio timeout so
            # a slow DDGS response or OpenAI latency spike never hangs the tool call.
            # Use claim_text when provided (so it matches eif_calibrate's lookup key);
            # fall back to hypothesis when claim_text is not supplied.
            _cep_probe_text = claim_text if claim_text else hypothesis
            cep_result = await asyncio.wait_for(
                asyncio.to_thread(
                    run_causal_evidence_probe,
                    claim_text=_cep_probe_text,
                    causal_level=causal_level,
                    consequence=consequence,
                    llm_fn=_llm_fn,
                ),
                timeout=3.0,
            )
        except TimeoutError:
            _log.warning(
                "CEP timed out (> 3 s) for probe %r - skipped (CG5)", _cep_probe_text[:80]
            )
        except Exception as _cep_exc:  # noqa: BLE001
            _log.warning("CEP skipped (non-fatal): %s", _cep_exc)

    # CG4: persist CEP result in session so eif_calibrate can apply posterior_delta.
    # Store under BOTH hypothesis and claim_text (when provided) so the lookup in
    # eif_calibrate (which keys by claim_text) reliably finds the result.
    # R5-03: also persist the full CausalGateResult for assemble_record.
    sess_cg = await session_store.get_session(session_id)
    _new_cep_results = dict(sess_cg.cep_results)
    if cep_result is not None:
        cep_dict = cep_result.model_dump()
        _new_cep_results[hypothesis] = cep_dict
        if claim_text and claim_text != hypothesis:
            _new_cep_results[claim_text] = cep_dict
    await session_store.update_session(
        session_id,
        cep_results=_new_cep_results,
        last_causal_gate=result.model_dump(),
    )

    _log.info(
        "TOOL  eif_causal_gate  session=%s  level=%s  verdict=%s  confounders=%d  "
        "active_discovered=%d  iris_full=%s  cep=%s",
        session_id[:8], causal_level, verdict, len(confounders),
        len(active_confounders), iris_full_pipeline,
        cep_result.verdict if cep_result else "SKIPPED",
    )

    response = {**result.model_dump(), "discovered_confounders": active_confounders}
    if causal_graph is not None:
        response["causal_graph"] = causal_graph.model_dump()
    if cep_result is not None:
        response["causal_evidence"] = cep_result.model_dump()
    else:
        response["causal_evidence"] = None
    return response


@mcp.tool(
    name="eif_calibrate",
    description=(
        "ADVANCED: Compute the Bayesian posterior for a claim given collected evidence. "
        "Call after eif_falsify once you have evidence. Uses empirical Bayes priors when "
        "calibration history reaches >= 10 prior calibrations in the session (PRIOR_EMPIRICAL_MIN). "
        "Use eif_verify instead if you want the full pipeline in one call. "
        "Parameters: session_id, claim_text, evidence[] (list of evidence strings), "
        "prior (optional float 0–1 - defaults to type-based prior), "
        "evidence_supports (required bool - True if evidence supports claim, False if it contradicts), "
        "likelihood_estimate (optional float - caller-supplied likelihood override), "
        "consequence_of_wrong ('LOW'/'MEDIUM'/'HIGH' - default MEDIUM), "
        "evidence_tier (optional 'P1'/'P2'/'P3'/'P4' - direct-observation tiers bypass the domain ceiling). "
        "Pass evidence_tier ('P1'/'P2'/'P3'/'P4') to exempt direct-observation evidence from domain ceiling "
        "clamps (F1C3): only P1/P2 (direct observation / experiment) bypass the healthcare/engineering "
        "posterior ceiling. P3 (web search) and P4 (parametric) are subject to the ceiling "
        "(eif_v5_evidence_trust_weighting TW6). "
        "ECE note: ece_label_grounded reflects whether per-session outcomes align within this session "
        "(requires labeled outcome records for THIS session via eif_record_outcome). The global ECE "
        "state (eif_calibration_report) counts records across all sessions - these two can differ. "
        "Returns: posterior (0–1), confidence_tier (HIGH/MEDIUM/LOW), ece_score (nullable until history exists), "
        "conformal_coverage, prior_strategy, calibration_warning (when ECE not yet label-grounded), "
        "ece_label_grounded (bool), domain_clamp_applied (bool). "
        "Also includes full CalibrationResult schema fields: claim_text, prior, likelihood, "
        "calibration_history_size, consequence_of_wrong. "
        "Note: conformal_coverage is computed from the session history before this call's result "
        "is appended; it reflects coverage over prior rounds only (CONFORMAL_MIN_HISTORY=20 pairs required)."
    ),
)
async def eif_calibrate(
    session_id: str,
    claim_text: str,
    evidence: list[str],
    prior: float | None = None,
    evidence_supports: bool | None = None,
    likelihood_estimate: float | None = None,
    consequence_of_wrong: str = "MEDIUM",
    evidence_tier: str | None = None,
) -> dict:
    """Phase 3: CALIBRATE - compute Bayesian posterior."""
    from eif.calibrate.bayesian import compute_posterior
    from eif.calibrate.conformal import compute_conformal_coverage
    from eif.calibrate.prior_strategy import empirical_bayes_prior, select_prior_strategy

    if not evidence:
        raise ValueError("evidence cannot be empty")

    sess = await session_store.get_session(session_id)
    history = sess.calibration_history
    history_size = len(history)

    if prior is not None and not (0.0 <= prior <= 1.0):
        raise ValueError(f"prior must be in [0, 1], got {prior}")

    strategy, _ = select_prior_strategy(prior is not None, history_size)

    if prior is None:
        if strategy == "empirical_bayes" and history:
            prior = empirical_bayes_prior([c.posterior for c in history])
        else:
            prior = 0.5

    if evidence_supports is None:
        raise ValueError(
            "evidence_supports is required: pass True if the evidence supports the claim, "
            "False if it contradicts. Inspect your evidence list and determine the direction manually."
        )

    posterior, likelihood = compute_posterior(prior, evidence_supports, likelihood_estimate)

    if posterior >= 0.8:
        confidence_tier = "HIGH"
    elif posterior >= 0.4:
        confidence_tier = "MEDIUM"
    else:
        confidence_tier = "LOW"

    # F1C1: label-grounded ECE - load real outcomes from the cross-session store
    # and pass them as outcome_history so compute_ece uses labeled data when >= 30 exist.
    from eif.calibrate.ece import apply_domain_ceiling
    from eif.calibrate.ece import compute_ece as compute_ece_v2  # noqa: PLC0415
    from eif.record.outcome_store import load_outcomes  # noqa: PLC0415
    _session_outcomes = [
        r.outcome for r in load_outcomes() if r.session_id == session_id
    ]
    # Alignment contract: outcomes are matched to calibration history by insertion order
    # (index 0 of outcomes → index 0 of history). This is correct when eif_record_outcome
    # is called once per provenance record in the same order decisions were made.
    # When outcomes are recorded out-of-order or at coarser granularity than calibrations,
    # ECE may be approximate. Log a warning when counts differ.
    if _session_outcomes and len(_session_outcomes) != len(history):
        _log.warning(
            "CalibrateECE: %d outcome(s) vs %d calibration(s) for session %s - "
            "alignment is by insertion order (best-effort)",
            len(_session_outcomes), len(history), session_id[:8],
        )
    _outcome_history: list[bool | None] = (
        (_session_outcomes + [None] * len(history))[:len(history)]
        if _session_outcomes else None  # type: ignore[assignment]
    )
    ece_result = compute_ece_v2(history, outcome_history=_outcome_history) if history else None
    ece_score = ece_result.ece if ece_result else None
    calibration_warning = ece_result.calibration_warning if ece_result else None
    conformal = compute_conformal_coverage(history)

    # Normalize evidence_tier: callers may pass short forms ('P1', 'P2', 'P3', 'P4').
    # apply_domain_ceiling expects the canonical internal strings.
    _TIER_NORM: dict[str, str] = {
        "P1": "P1_NATIVE_CODE",
        "P2": "P2_EXPERIMENTAL",
        "P3": "P3_WEB_SEARCH",
        "P4": "P4_PARAMETRIC",
    }
    _normalized_tier = _TIER_NORM.get((evidence_tier or "").upper(), evidence_tier)

    # F1C3: physics-informed domain ceiling - pass normalized tier so direct-observation
    # tiers P1/P2 are exempted (P3/P4 are subject to the ceiling; eif_v5 TW6).
    # R6-08: when chain is empty (granular pipeline before first eif_record), fall back to
    # claim_text keywords so the ceiling is applied consistently from the first calibration.
    domain_clamp = False
    _domain_text = (
        sess.provenance_chain[-1].decision.lower()
        if sess.provenance_chain
        else claim_text.lower()
    )
    for dom in ("healthcare", "medical", "engineering", "aviation", "nuclear"):
        if dom in _domain_text:
            posterior, domain_clamp = apply_domain_ceiling(posterior, dom, _normalized_tier)
            if domain_clamp:
                confidence_tier = "HIGH" if posterior >= 0.8 else ("MEDIUM" if posterior >= 0.4 else "LOW")
            break

    # CG4: apply CEP posterior_delta if a matching causal evidence probe ran for this claim.
    # The delta is a signed float (e.g. SUPPORTS → +0.15, CONTRADICTS → -0.20).
    # We clamp the adjusted posterior to [0.01, 0.99] to avoid boundary degeneracy.
    _cep_delta = 0.0
    _cep_record = sess.cep_results.get(claim_text)
    if _cep_record and isinstance(_cep_record.get("posterior_delta"), float):
        _cep_delta = float(_cep_record["posterior_delta"])
        _pre_cep_posterior = posterior
        posterior = max(0.01, min(0.99, posterior + _cep_delta))
        if _cep_delta != 0.0:
            _log.info(
                "CG4 posterior_delta applied for claim %r: %.3f + %.3f = %.3f",
                claim_text[:60], _pre_cep_posterior, _cep_delta, posterior,
            )
        # Recompute confidence tier after delta
        if posterior >= 0.8:
            confidence_tier = "HIGH"
        elif posterior >= 0.4:
            confidence_tier = "MEDIUM"
        else:
            confidence_tier = "LOW"

    result = CalibrationResult(
        claim_text=claim_text,
        prior=prior,
        likelihood=likelihood,
        posterior=posterior,
        ece_score=ece_score,
        conformal_coverage=conformal,
        confidence_tier=confidence_tier,
        prior_strategy=strategy,
        calibration_history_size=history_size,
        domain_clamp_applied=domain_clamp,
        consequence_of_wrong=consequence_of_wrong,  # type: ignore[arg-type]
    )

    new_history = history + [result]
    await session_store.update_session(session_id, calibration_history=new_history)

    _log.info(
        "TOOL  eif_calibrate  session=%s  prior=%.3f  posterior=%.3f  tier=%s  clamp=%s  ece_grounded=%s",
        session_id[:8], prior, posterior, confidence_tier, domain_clamp,
        ece_result.label_grounded if ece_result else False,
    )

    result_dict = result.model_dump()
    if calibration_warning:
        result_dict["calibration_warning"] = calibration_warning
    # R6-09: always include ece_label_grounded so callers don't have to guard for missing field.
    result_dict["ece_label_grounded"] = ece_result.label_grounded if ece_result else False
    return result_dict


@mcp.tool(
    name="eif_challenge",
    description=(
        "ADVANCED: Structure an adversarial challenge to a claim using an independent critic. "
        "Call when posterior is uncertain (0.4–0.7) or when the decision is high-stakes. "
        "Parameters: session_id, claim_text, current_posterior, "
        "critic_model (optional - model name for the critic LLM), "
        "critic_approach (optional - approach hint for the critic prompt), "
        "counter_evidence[] (optional - supply if you already have contradicting evidence), "
        "num_critics (int - run tournament with N critics; default 1; ignored when counter_evidence supplied), "
        "replication_mode (optional - pass 'DASES' to also run adversarial replicator F8). "
        "Requires OPENAI_API_KEY to invoke a real independent critic (DIFFERENT_OBJECTIVE tier). "
        "WITHOUT an API key: falls back to a challenge protocol only - no live LLM critic runs, "
        "critic_independence is set to NONE, and self_evaluation_flag=True. "
        "In this case, challenge_result.critic_independence == NONE and no counter_evidence is generated "
        "unless you supply it. The ProvenanceRecord.contrary_evidence_considered field (assembled later "
        "by eif_record) will be False unless counter_evidence is passed here "
        "(C9 OR-logic: True when independent critic ran OR counter_evidence supplied). "
        "Use eif_verify instead if you want the full pipeline in one call. "
        "Pass counter_evidence if you already have contradicting evidence; otherwise generates challenge protocol. "
        "Pass num_critics > 1 to run a tournament (AI Co-Scientist style): multiple adversarial critics compete, "
        "their objections are merged, deduplicated, and ranked by specificity. Requires OPENAI_API_KEY. "
        "Note: tournament mode is disabled when counter_evidence is supplied - in that case num_critics_used=1 "
        "regardless of the num_critics parameter. "
        "Returns: challenge_result (full ChallengeResult schema - verdict (SURVIVES/DEFEATED/NEEDS_REVISION), "
        "self_evaluation_flag, critic_independence, hardening_score, claim_text, counter_evidence_found, "
        "counter_evidence[], competing_hypothesis), "
        "challenge_protocol (markdown protocol text - present when counter_evidence not supplied), "
        "num_critics_used, "
        "replication_result (only when replication_mode='DASES', F8C3)."
    ),
)
async def eif_challenge(
    session_id: str,
    claim_text: str,
    current_posterior: float,
    critic_model: str | None = None,
    critic_approach: str | None = None,
    counter_evidence: list[str] | None = None,
    num_critics: int = 1,
    replication_mode: str | None = None,
) -> dict:
    """Phase 4: CHALLENGE - adversarial probe.

    V2: pass replication_mode='DASES' to also run the adversarial replicator
    (F8, arXiv:2603.29045). Opt-in only due to latency cost.
    """
    import os

    from eif.challenge.protocol import build_challenge_result, generate_protocol
    from eif.schemas import CriticIndependence

    if not (0.0 <= current_posterior <= 1.0):
        raise ValueError(f"current_posterior must be in [0, 1], got {current_posterior}")

    num_critics = max(1, int(num_critics))
    challenge_result = None
    protocol_text = None

    # Tournament mode: use real LLM critics when API key is available
    has_api_key = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    if has_api_key and counter_evidence is None:
        from eif.challenge.multi_critic import run_multi_critic_challenge
        challenge_result = run_multi_critic_challenge(
            claim_text=claim_text,
            generator_model=critic_model,
            posterior=current_posterior,
            num_critics=num_critics,
        )
    else:
        approach: CriticIndependence | None = None
        if critic_approach:
            approach = critic_approach  # type: ignore[assignment]

        challenge_result = build_challenge_result(
            claim_text=claim_text,
            critic_model=critic_model,
            counter_evidence=counter_evidence,
            critic_approach=approach,
        )

        if counter_evidence is None:
            protocol_text = generate_protocol(claim_text, current_posterior)

    # F8: DASES adversarial replication (opt-in)
    replication_result = None
    if replication_mode and replication_mode.upper() == "DASES":
        from eif.challenge.replicator import run_adversarial_replication  # noqa: PLC0415
        replication_result = run_adversarial_replication(
            claim_text=claim_text,
            supporting_evidence=counter_evidence or [],
        )

    _log.info(
        "TOOL  eif_challenge  session=%s  independence=%s  verdict=%s  self_eval=%s  num_critics=%d  dases=%s",
        session_id[:8], challenge_result.critic_independence,
        challenge_result.verdict, challenge_result.self_evaluation_flag, num_critics,
        replication_result is not None,
    )

    # Persist last challenge on session so eif_record can pass it into assemble_record (C9)
    _challenge_sess = await session_store.get_session(session_id)
    await session_store.update_session(
        session_id,
        last_challenge=challenge_result.model_dump(),
    )

    result = {
        "challenge_result": challenge_result.model_dump(),
        "challenge_protocol": protocol_text,
        "num_critics_used": num_critics if has_api_key and counter_evidence is None else 1,
    }
    if replication_result is not None:
        result["replication_result"] = replication_result.model_dump()
    return result


@mcp.tool(
    name="eif_update",
    description=(
        "ADVANCED: Run a sequential Bayesian update given new evidence. "
        "Call after eif_challenge when new counter-evidence arrives. "
        "Parameters: session_id, hypothesis (claim text), current_posterior (float 0–1), "
        "new_evidence (text summary of new evidence), "
        "evidence_supports (bool - True if evidence supports, False if it contradicts), "
        "decision_value (optional float - economic value of the decision for cost-weighted EIG), "
        "delta_min (optional float - EIG stopping threshold; default 0.01 nats). "
        "Computes Expected Information Gain (EIG) and applies the EIG stopping rule - "
        "if EIG < delta_min (default 0.01 nats), further evidence collection adds negligible value. "
        "Note: only the EIG_BELOW_THRESHOLD stopping rule is available here; SPRT_BOUNDARY and "
        "COST_EXCEEDS_VALUE require the full pipeline via eif_verify. "
        "Use eif_verify instead if you want all stopping rules in one call. "
        "Returns: updated_posterior, eig, stopping_rule_triggered, stopping_reason, "
        "recommendation (MAINTAIN_COURSE / RETURN_TO_DECLARE / ESCALATE), "
        "paradigm_alert (PIEVO drift - fires when >= 3 consecutive same-direction updates AND mean "
        "|shift| >= PARADIGM_MIN_AVG_SHIFT (0.04); null otherwise; when non-null: full "
        "ParadigmRevisionAlert schema - session_id, direction (DOWN/UP/MIXED), "
        "consecutive_updates, avg_posterior_shift, affected_claims[], recommendation, detected_at). "
        "Also includes full UpdateResult schema fields: hypothesis, prior_posterior, new_evidence."
    ),
)
async def eif_update(
    session_id: str,
    hypothesis: str,
    current_posterior: float,
    new_evidence: str,
    evidence_supports: bool,
    decision_value: float | None = None,
    delta_min: float = EIG_THRESHOLD,
) -> dict:
    """Phase 5: UPDATE - sequential Bayes update with stopping rules."""
    from eif.schemas import UpdateResult
    from eif.update.eig import compute_eig
    from eif.update.paradigm import check_paradigm_revision
    from eif.update.posterior import sequential_update
    from eif.update.stopping import evaluate_stopping

    if not (0.0 <= current_posterior <= 1.0):
        raise ValueError(f"current_posterior must be in [0, 1], got {current_posterior}")

    new_posterior, _ = sequential_update(current_posterior, evidence_supports)
    eig = compute_eig(current_posterior, new_posterior)
    triggered, reason = evaluate_stopping(eig, delta_min=delta_min)

    if new_posterior >= THRESHOLD_ACT:
        recommendation = "MAINTAIN_COURSE"
    elif new_posterior <= THRESHOLD_HALT:
        recommendation = "ESCALATE"
    else:
        recommendation = "RETURN_TO_DECLARE"

    result = UpdateResult(
        hypothesis=hypothesis,
        prior_posterior=current_posterior,
        new_evidence=new_evidence,
        updated_posterior=new_posterior,
        eig=eig,
        stopping_rule_triggered=triggered,
        stopping_reason=reason,
        recommendation=recommendation,
    )

    # Persist update to session so programme_health and paradigm checks have history
    sess = await session_store.get_session(session_id)
    new_updates = list(sess.updates) + [result]
    await session_store.update_session(session_id, updates=new_updates)

    # PIEVO paradigm drift check - fires when >= 3 consecutive same-direction updates
    paradigm_alert = check_paradigm_revision(new_updates, session_id=session_id)

    # Persist paradigm_alert so eif_record strategy memory includes it even when
    # eif_programme_health is not called in the same session (R15-04).
    if paradigm_alert is not None:
        sess2 = await session_store.get_session(session_id)
        new_alerts = list(sess2.paradigm_alerts) + [paradigm_alert]
        await session_store.update_session(session_id, paradigm_alerts=new_alerts)

    _log.info(
        "TOOL  eif_update  session=%s  prior=%.3f  posterior=%.3f  eig=%.4f  stop=%s  rec=%s  paradigm_alert=%s",
        session_id[:8], current_posterior, new_posterior, eig, triggered, recommendation,
        paradigm_alert.direction if paradigm_alert else None,
    )

    return {
        **result.model_dump(),
        "paradigm_alert": paradigm_alert.model_dump() if paradigm_alert else None,
    }


@mcp.tool(
    name="eif_explain",
    description=(
        "ADVANCED: Validate an explanation using the hard-to-vary criterion (Deutsch). "
        "A hard-to-vary explanation is one where changing any detail breaks the fit to evidence. "
        "Call after eif_update when the posterior is stable and you need a documented explanation artifact. "
        "Use eif_verify instead if you want the full pipeline in one call. "
        "Parameters: session_id, prior_explanation (previous explanation text), "
        "new_explanation (updated mechanism), details[] (list of sub-claim dicts - each must be "
        "specific and independently checkable; vague details fail), "
        "testable_predictions[] (list of prediction strings derivable from the explanation), "
        "disconfirming_evidence (optional - evidence that challenges the explanation), "
        "reach ('LOCAL'/'GLOBAL' - scope of the explanation; optional), "
        "reach_implications (text describing global implications if reach='GLOBAL'; optional), "
        "corroborated (bool - whether explanation is independently corroborated; default False), "
        "system_context (string describing the specific system/domain to enable domain-specificity gate). "
        "Optional: pass system_context (e.g. 'FinCorp risk engine running on AWS EKS with HIPAA SaMD') "
        "to enable the v4.1 domain-specificity gate (S14): details that reference none of the "
        "system-specific anchor tokens are flagged as domain-agnostic. Deterministic, no LLM call. "
        "Returns: artifact (full ExplanationArtifact schema - hard_to_vary_verdict PASS/FAIL, "
        "prior_explanation, new_explanation, details, testable_predictions, reach, corroborated, "
        "disconfirming_evidence, domain_specificity_verdict), failed_details[], verdict."
    ),
)
async def eif_explain(
    session_id: str,
    prior_explanation: str,
    new_explanation: str,
    details: list[dict],
    testable_predictions: list[str],
    disconfirming_evidence: str | None = None,
    reach: str | None = None,
    reach_implications: str | None = None,
    corroborated: bool = False,
    system_context: str | None = None,
) -> dict:
    """Phase 5.5: EXPLAIN - hard-to-vary validation (+ optional v4.1 domain-specificity gate)."""
    from eif.explain.artifact import build_artifact

    artifact, failed_details = build_artifact(
        prior_explanation=prior_explanation,
        new_explanation=new_explanation,
        details=details,
        testable_predictions=testable_predictions,
        disconfirming_evidence=disconfirming_evidence,
        reach=reach,  # type: ignore[arg-type]
        reach_implications=reach_implications,
        corroborated=corroborated,
        system_context=system_context,
    )

    _log.info(
        "TOOL  eif_explain  session=%s  verdict=%s  failed=%d  predictions=%d",
        session_id[:8], artifact.hard_to_vary_verdict, len(failed_details),
        len(testable_predictions),
    )

    # R5-03: persist explanation artifact so eif_record can pass it to assemble_record.
    try:
        await session_store.update_session(session_id, last_explanation=artifact.model_dump())
    except Exception as _ex_exc:  # noqa: BLE001
        _log.warning("eif_explain: session persist failed (non-fatal): %s", _ex_exc)

    return {
        "artifact": artifact.model_dump(),
        "verdict": artifact.hard_to_vary_verdict,
        "failed_details": failed_details,
    }


@mcp.tool(
    name="eif_record",
    description=(
        "ADVANCED: Assemble and store a provenance record for the current decision. "
        "Always call this at the end of the pipeline - it is the audit trail. "
        "Parameters: session_id, decision (text of the agent decision being recorded), "
        "models_used[] (model names that produced claims), tools_invoked[] (EIF/agent tools used), "
        "human_oversight (NOT_NEEDED or ESCALATED - default NOT_NEEDED). "
        "Maps the decision to EU AI Act compliance articles via record/compliance.py::map_compliance: "
        "Art. 9 (risk management - fires on HIGH-consequence claims OR causal_unverified), "
        "Art. 12 (record-keeping - always fires), "
        "Art. 13 (transparency - fires when an explanation artifact is attached), "
        "Art. 14 (human oversight - fires on ESCALATED). "
        "The mapping is persisted on the returned ProvenanceRecord as articles_covered "
        "(dict[article_label → reason_lines]) so eif_compliance_report renders without recomputing. "
        "Use eif_verify instead if you want the full pipeline in one call. "
        "Returns: record_id, record (full ProvenanceRecord model dump - key audit fields include "
        "metric_quality_flags[], input_guard (IG6 persisted InputGuardResult), calibration[], updates[], "
        "sprt_results[], causal_evidence_result; outcome_observed/outcome_recorded_at are legacy - "
        "use eif_record_outcome for ECE feedback instead), "
        "chain_length, contrary_evidence_considered, stale_evidence_warnings[], harked_conditions[], "
        "strategy_tip, research_object (DeepTRACE 8-dimension audit, F4), "
        "isc_disclosure (ISC AI taxonomy, F5)."
    ),
)
async def eif_record(
    session_id: str,
    decision: str,
    models_used: list[str],
    tools_invoked: list[str],
    human_oversight: str = "NOT_NEEDED",
) -> dict:
    """Phase 6: RECORD - store provenance record."""
    from eif.record.chain import append_to_chain
    from eif.record.provenance import assemble_record

    if not decision:
        raise ValueError("decision string cannot be empty")

    sess = await session_store.get_session(session_id)

    # R5-02: prefer last_registry (written by eif_declare/eif_verify) over the chain-tail
    # fallback so granular-pipeline callers always get a populated AssumptionRegistry.
    registry = None
    if sess.last_registry:
        from eif.schemas import AssumptionRegistry  # noqa: PLC0415
        try:
            registry = AssumptionRegistry.model_validate(sess.last_registry)
        except Exception as _reg_exc:  # noqa: BLE001
            _log.warning("eif_record: could not restore last_registry (non-fatal): %s", _reg_exc)
    if registry is None:
        if sess.provenance_chain:
            registry = sess.provenance_chain[-1].registry
        else:
            from eif.schemas import AssumptionRegistry  # noqa: PLC0415
            registry = AssumptionRegistry(session_id=session_id, decision=decision)

    # R4-CR-02: reconstruct CausalEvidenceResult and ChallengeResult from session
    # so assemble_record can set causal_unverified (CG6) and contrary_evidence_considered (C9).
    _causal_evidence_result = None
    if sess.cep_results:
        from eif.schemas import CausalEvidenceResult  # noqa: PLC0415
        # R5-08: prefer the CEP result whose key matches the decision text (avoids attaching
        # the wrong probe under multiple causal claims). Fall back to the last stored result.
        _cep_dict_match = (
            sess.cep_results.get(decision)
            or next(
                (v for k, v in sess.cep_results.items() if decision.startswith(k[:40]) or k[:40] in decision[:80]),
                None,
            )
            or list(sess.cep_results.values())[-1]
        )
        try:
            _causal_evidence_result = CausalEvidenceResult.model_validate(_cep_dict_match)
        except Exception as _cep_exc:  # noqa: BLE001
            _log.warning("eif_record: could not reconstruct CausalEvidenceResult (non-fatal): %s", _cep_exc)

    _challenge_result = None
    if sess.last_challenge:
        from eif.schemas import ChallengeResult  # noqa: PLC0415
        try:
            _challenge_result = ChallengeResult.model_validate(sess.last_challenge)
        except Exception as _ch_exc:  # noqa: BLE001
            _log.warning("eif_record: could not reconstruct ChallengeResult (non-fatal): %s", _ch_exc)

    # R5-03: reconstruct phase artifacts (falsification conditions, SPRT results,
    # causal gate, explanation) persisted by the granular tools so assemble_record
    # can include them in the immutable audit trail.
    _falsification_conditions = None
    if sess.last_falsification_conditions:
        from eif.schemas import FalsificationCondition  # noqa: PLC0415
        try:
            _falsification_conditions = [
                FalsificationCondition.model_validate(d)
                for d in sess.last_falsification_conditions
            ]
        except Exception as _fc_exc:  # noqa: BLE001
            _log.warning("eif_record: could not restore falsification_conditions (non-fatal): %s", _fc_exc)

    _sprt_results = None
    if sess.last_sprt_results:
        from eif.schemas import SPRTResult  # noqa: PLC0415
        try:
            _sprt_results = [SPRTResult.model_validate(d) for d in sess.last_sprt_results]
        except Exception as _sprt_exc:  # noqa: BLE001
            _log.warning("eif_record: could not restore sprt_results (non-fatal): %s", _sprt_exc)

    _causal_gate = None
    if sess.last_causal_gate:
        from eif.schemas import CausalGateResult  # noqa: PLC0415
        try:
            _causal_gate = CausalGateResult.model_validate(sess.last_causal_gate)
        except Exception as _cg_exc:  # noqa: BLE001
            _log.warning("eif_record: could not restore causal_gate (non-fatal): %s", _cg_exc)

    _explanation = None
    if sess.last_explanation:
        from eif.schemas import ExplanationArtifact  # noqa: PLC0415
        try:
            _explanation = ExplanationArtifact.model_validate(sess.last_explanation)
        except Exception as _ex_exc:  # noqa: BLE001
            _log.warning("eif_record: could not restore explanation (non-fatal): %s", _ex_exc)

    record, stale_warnings, harked_conditions = assemble_record(
        session_id=session_id,
        decision=decision,
        registry=registry,
        falsification_conditions=_falsification_conditions,  # R5-03: FALSIFY artifacts
        sprt_results=_sprt_results,  # R5-03: SPRT artifacts
        causal_gate=_causal_gate,  # R5-03: CAUSAL_GATE artifact
        calibration=list(sess.calibration_history),  # F13: needed by Extension B
        causal_evidence_result=_causal_evidence_result,  # CG6: CAUSAL_UNVERIFIED flag
        challenge=_challenge_result,  # C9: contrary_evidence_considered
        updates=list(sess.updates),  # strategy/research path
        explanation=_explanation,  # R5-03: EXPLAIN artifact
        models_used=models_used,
        tools_invoked=tools_invoked,
        human_oversight=human_oversight,  # type: ignore[arg-type]
        metric_quality_flags=list(getattr(sess, "metric_quality_flags", [])),  # F17
        input_guard=getattr(sess, "last_input_guard", None),  # IG6
    )

    updated_sess = append_to_chain(sess, record)
    await session_store.update_session(
        session_id,
        provenance_chain=updated_sess.provenance_chain,
    )

    # R8-02: compute final_route ONCE before any try-blocks so it is never reset to "ACT"
    # inside a try-block that might throw. ISC disclosure and research_object both read it.
    # R6-07: derive from calibration when updates empty (HALT-from-calibrate sessions).
    final_route = "ACT"
    halt_reason: str | None = None
    if sess.updates:
        _last_update = sess.updates[-1]
        if _last_update.recommendation == "ESCALATE":
            final_route = "HALT"
            halt_reason = _last_update.stopping_reason
        elif _last_update.recommendation == "RETURN_TO_DECLARE":
            final_route = "REVISE"
    elif sess.calibration_history:
        _min_post_shared = min(c.posterior for c in sess.calibration_history)
        if _min_post_shared < THRESHOLD_HALT:
            final_route = "HALT"
        elif _min_post_shared < THRESHOLD_ACT:
            final_route = "REVISE"

    # EvoScientist cross-session strategic memory - record outcomes for future sessions
    strategy_tip: str | None = None
    try:
        from eif.memory.strategy import load_strategy_memory

        # Derive domain from decision text via keyword match
        dec_lower = decision.lower()
        if any(w in dec_lower for w in ("health", "medical", "clinical", "patient", "drug")):
            domain = "healthcare"
        elif any(w in dec_lower for w in ("financ", "invest", "market", "trade", "risk")):
            domain = "finance"
        elif any(w in dec_lower for w in ("legal", "law", "court", "regulat", "compli")):
            domain = "legal"
        elif any(w in dec_lower for w in ("engineer", "system", "infrastructure", "software")):
            domain = "engineering"
        else:
            domain = "generic"

        # Decisive evidence tier: first P-tier keyword found in stale warnings or decisions
        decisive_tier: str | None = None
        for tier in ("P1", "P2", "P3", "P4"):
            if any(tier in e for e in (stale_warnings or []) + [decision]):
                decisive_tier = tier
                break

        # Cumulative session flag: True if any paradigm alert fired this session.
        # For per-turn granularity, check sess.updates[-1].paradigm_alert if needed.
        paradigm_fired = len(sess.paradigm_alerts) > 0

        mem = load_strategy_memory()
        # R7-09: use min calibration posterior when updates empty to mirror the
        # final_route derivation above; avoids a misleading 0.5 default.
        _final_post: float
        if sess.updates:
            _final_post = sess.updates[-1].updated_posterior
        elif sess.calibration_history:
            _final_post = min(c.posterior for c in sess.calibration_history)
        else:
            _final_post = 0.5
        mem.record_session(
            domain=domain,
            final_route=final_route,
            decisive_tier=decisive_tier,
            halt_reason=halt_reason,
            final_posterior=_final_post,
            paradigm_alert=paradigm_fired,
        )
        strategy_tip = mem.get_tip(domain)
    except Exception as exc:  # noqa: BLE001
        _log.warning("strategy_memory.record_session failed (non-fatal): %s", exc)

    # F4: Research Object + DeepTRACE 8-dimension audit (V2)
    research_object = None
    try:
        # R7-04: pass EIF phase IDs (not raw tool names) so ResearchObject correctly maps
        # to DeepTRACE dimensions; _infer_phases reads record artifacts to identify phases run.
        from eif.record.isc_disclosure import _infer_phases as _isc_infer_phases  # noqa: PLC0415
        from eif.record.research_object import build_research_object  # noqa: PLC0415
        _ro_phases = _isc_infer_phases(record)
        if session_id in _sycophancy_gates and "SYCOPHANCY_GATE" not in _ro_phases:
            _ro_phases.append("SYCOPHANCY_GATE")
        # R8-02: use the already-computed final_route (hoisted above) - do NOT reset here.
        research_object = build_research_object(
            record=record,
            verdict=final_route,
            phases_run=_ro_phases,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("build_research_object failed (non-fatal): %s", exc)

    # F5: ISC AI disclosure taxonomy (V2, draft-2026)
    isc_disclosure = None
    try:
        from eif.record.isc_disclosure import (  # noqa: PLC0415
            _infer_phases,
            generate_isc_disclosure,
        )
        # R6-13: build explicit phases list so SYCOPHANCY_GATE and INPUT_GUARD appear
        # even when not in tools_invoked. SYCOPHANCY_GATE is in-process (no record field);
        # detect from the session-level sycophancy gate registry.
        _isc_phases = _infer_phases(record)
        if session_id in _sycophancy_gates and "SYCOPHANCY_GATE" not in _isc_phases:
            _isc_phases.append("SYCOPHANCY_GATE")
        # R8-02: always pass final_route directly - never "UNKNOWN" - so F5C2 human_required
        # fires correctly on HALT regardless of whether build_research_object succeeded.
        isc_disclosure = generate_isc_disclosure(
            record=record,
            verdict=final_route,
            phases_run=_isc_phases,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("generate_isc_disclosure failed (non-fatal): %s", exc)

    _log.info(
        "TOOL  eif_record  session=%s  record=%s  chain_length=%d  stale=%d  harked=%d  "
        "deeptraceScore=%.3f  isc_entries=%d",
        session_id[:8], record.record_id[:8], len(updated_sess.provenance_chain),
        len(stale_warnings), len(harked_conditions),
        research_object.dimensions.overall_score if research_object else 0.0,
        len(isc_disclosure.entries) if isc_disclosure else 0,
    )

    return {
        "record_id": record.record_id,
        "record": record.model_dump(),
        "chain_length": len(updated_sess.provenance_chain),
        "contrary_evidence_considered": record.contrary_evidence_considered,
        "stale_evidence_warnings": stale_warnings,
        "harked_conditions": harked_conditions,
        "strategy_tip": strategy_tip,
        "research_object": research_object.model_dump() if research_object else None,
        "isc_disclosure": isc_disclosure.model_dump() if isc_disclosure else None,
    }


@mcp.tool(
    name="eif_replicate",
    description=(
        "ADVANCED: Structure a replication protocol, evaluate replication results, AND run "
        "Extension B independent convergent replication (V3). "
        "Call after eif_record when the claim is important and can be independently replicated. "
        "Parameters: session_id, claim_text, original_inputs{} (dict of inputs used to produce the claim), "
        "isolation_strategy ('SELF_CONSISTENCY' default or 'INDEPENDENT_SAMPLE'/'INDEPENDENT'), "
        "replication_results[] (optional list of replicated response strings to evaluate), "
        "n_replicates (int, default 3 - number of replication runs in the protocol), "
        "replication_criterion ('STATISTICAL' default - criteria for agreement), "
        "run_independent_replication (bool, default False - triggers Extension B), "
        "record_id (optional str - provenance record ID required for Extension B). "
        "Supports SELF_CONSISTENCY (same model, different seed) and INDEPENDENT (different model) strategies.\n\n"
        "Extension B (automatic when run_independent_replication=True and record_id is provided):\n"
        "  Re-derives the routing verdict from a flat prior (P(H)=0.5) using the same likelihoods.\n"
        "  CONVERGENT = same routing bucket (ACT/REVISE/HALT) from both derivations.\n"
        "  DIVERGENT  = routing depends on the empirical prior → human review required.\n\n"
        "Use eif_verify instead if you want the full pipeline in one call. "
        "Returns: protocol (text), verdict (REPLICATED/PARTIAL/DIVERGED/null), "
        "agreement_rate (float or null), divergence_details[], replication_type, "
        "independent_replication (when run_independent_replication=True - full "
        "IndependentReplicationResult schema: session_id, provenance_record_id, "
        "original_routing, independent_routing, original_min_posterior, independent_min_posterior, "
        "prior_sensitivity, agreement_type (CONVERGENT/DIVERGENT), diverged, "
        "human_review_required, claims_compared, notes, created_at; "
        "or {'error': 'record_id ... not found'} when record_id is not in session)."
    ),
)
async def eif_replicate(
    session_id: str,
    claim_text: str,
    original_inputs: dict,
    isolation_strategy: str = "SELF_CONSISTENCY",
    replication_results: list[str] | None = None,
    n_replicates: int = 3,
    replication_criterion: str = "STATISTICAL",
    run_independent_replication: bool = False,
    record_id: str | None = None,
) -> dict:
    """Phase 7: REPLICATE - structure, evaluate, and optionally run Extension B."""
    from eif.replicate.divergence import evaluate_replication
    from eif.replicate.protocol import generate_replication_protocol

    protocol, replication_type = generate_replication_protocol(
        claim_text=claim_text,
        original_inputs=original_inputs,
        isolation_strategy=isolation_strategy,
        n_replicates=n_replicates,
        replication_criterion=replication_criterion,
    )

    verdict = None
    agreement_rate = None
    divergence_details: list[str] = []

    if replication_results is not None:
        verdict, agreement_rate, divergence_details = evaluate_replication(
            claim_text=claim_text,
            replication_results=replication_results,
            replication_criterion=replication_criterion,
            replication_type=replication_type,
        )

    # Extension B: independent convergent replication (F13)
    independent_result = None
    if run_independent_replication and record_id:
        from eif.replicate.independent import run_independent_replication as _run_ir
        sess = await session_store.get_session(session_id)
        target_record = next(
            (r for r in sess.provenance_chain if r.record_id == record_id), None
        )
        if target_record is not None:
            ir = _run_ir(target_record)
            independent_result = ir.model_dump()
        else:
            independent_result = {"error": f"record_id {record_id!r} not found in session"}

    _log.info(
        "TOOL  eif_replicate  session=%s  type=%s  verdict=%s  agreement=%s  indep=%s",
        session_id[:8], replication_type, verdict, agreement_rate,
        independent_result.get("agreement_type") if independent_result and "error" not in independent_result else "n/a",
    )

    return {
        "protocol": protocol,
        "verdict": verdict,
        "agreement_rate": agreement_rate,
        "divergence_details": divergence_details,
        "replication_type": replication_type,
        "independent_replication": independent_result,
    }


@mcp.tool(
    name="eif_programme_health",
    description=(
        "ADVANCED: Assess whether the agent's reasoning programme is progressing or degenerating. "
        "A PROGRESSIVE programme makes novel predictions that are later confirmed. "
        "A DEGENERATIVE programme keeps patching failed predictions without new explanatory power. "
        "Call after >= 3 provenance records exist in the session. "
        "Returns: signals (novel_prediction_rate, confirmed_prediction_rate, patch_rate, oscillation_count, status), "
        "interpretation, recommendation, "
        "paradigm_alert (PIEVO drift detection - null when no drift detected), "
        "principle_revision_proposal (F3: full PrincipleRevisionProposal schema when paradigm degenerates - "
        "session_id, affected_principle, revision_direction, supporting_evidence[], confidence (capped 0.80 per F3C3), "
        "alternative_hypotheses[] (>= 2 per F3C1), requires_confirmation=True (advisory only, never auto-applied - F3C2), "
        "triggered_by_alert_direction, created_at; null when programme is not DEGENERATIVE)."
    ),
)
async def eif_programme_health(session_id: str) -> dict:
    """Phase 8: PROGRAMME_HEALTH - Lakatos health assessment."""
    from eif.programme.monitor import check_paradigm_health, compute_status
    from eif.programme.signals import compute_signals
    from eif.programme.status import derive_status_text

    sess = await session_store.get_session(session_id)

    if len(sess.provenance_chain) < 3:
        raise ValueError(
            f"Programme health requires >= 3 records, "
            f"got {len(sess.provenance_chain)}"
        )

    signals = compute_signals(sess.provenance_chain)
    status = compute_status(signals)
    signals_with_status = signals.model_copy(update={"status": status})
    interpretation, recommendation = derive_status_text(status, signals)

    # PIEVO paradigm drift check against the full UPDATE history for this session
    paradigm_alert = check_paradigm_health(sess.updates, session_id=session_id)
    if paradigm_alert:
        await session_store.update_session(
            session_id,
            programme=signals_with_status,
            paradigm_alerts=list(sess.paradigm_alerts) + [paradigm_alert],
        )
    else:
        await session_store.update_session(session_id, programme=signals_with_status)

    _log.info(
        "TOOL  eif_programme_health  session=%s  status=%s  novel=%.2f  confirmed=%.2f  patch=%.2f  paradigm=%s",
        session_id[:8], status, signals.novel_prediction_rate,
        signals.confirmed_prediction_rate, signals.patch_rate,
        paradigm_alert.direction if paradigm_alert else None,
    )

    # F3: PIEVO principle revision proposal (V2) - fires when paradigm alert detected
    principle_revision_proposal = None
    if paradigm_alert:
        try:
            from eif.programme.principle_revision import propose_principle_revision  # noqa: PLC0415
            all_claims = []
            for rec in sess.provenance_chain:
                all_claims.extend(rec.registry.known + rec.registry.assumed + rec.registry.guessed)
            principle_revision_proposal = propose_principle_revision(
                alert=paradigm_alert,
                claims=all_claims,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("propose_principle_revision failed (non-fatal): %s", exc)

    _log.info(
        "TOOL  eif_programme_health  session=%s  status=%s  novel=%.2f  confirmed=%.2f  patch=%.2f  "
        "paradigm=%s  revision_proposed=%s",
        session_id[:8], status, signals.novel_prediction_rate,
        signals.confirmed_prediction_rate, signals.patch_rate,
        paradigm_alert.direction if paradigm_alert else None,
        principle_revision_proposal is not None,
    )

    return {
        "signals": signals_with_status.model_dump(),
        "interpretation": interpretation,
        "recommendation": recommendation,
        "paradigm_alert": paradigm_alert.model_dump() if paradigm_alert else None,
        "principle_revision_proposal": (
            principle_revision_proposal.model_dump() if principle_revision_proposal else None
        ),
    }


@mcp.tool(
    name="eif_provenance",
    description=(
        "ADVANCED: Query the provenance chain for this session. "
        "Use format='summary' for a compact overview (decisions, assumptions, HALTs, compliance_status). "
        "Use format='full' to retrieve all records for export or audit. "
        "Pass record_id to retrieve a specific record by ID. "
        "For a formatted compliance report (EU AI Act ready, human-readable), use eif_compliance_report instead. "
        "Returns: summary dict OR records[] depending on format."
    ),
)
async def eif_provenance(
    session_id: str,
    record_id: str | None = None,
    format: str = "summary",
) -> dict:
    """Query the provenance chain."""
    from eif.programme.monitor import compute_status
    from eif.programme.signals import compute_signals

    sess = await session_store.get_session(session_id)

    if record_id is not None:
        matching = [r for r in sess.provenance_chain if r.record_id == record_id]
        if not matching:
            raise ValueError(f"record_id {record_id!r} not found in session {session_id!r}")
        return {"records": [r.model_dump() for r in matching]}

    if format == "full":
        return {"records": [r.model_dump() for r in sess.provenance_chain]}

    chain = sess.provenance_chain
    signals = compute_signals(chain)
    status = compute_status(signals)

    _log.info("TOOL  eif_provenance  session=%s  records=%d  format=%s", session_id[:8], len(chain), format)

    return {
        "summary": {
            "session_id": session_id,
            "decisions_recorded": len(chain),
            "assumptions_declared": sum(
                len(r.registry.known) + len(r.registry.assumed) + len(r.registry.guessed)
                for r in chain
            ),
            "known_count": sum(len(r.registry.known) for r in chain),
            "assumed_count": sum(len(r.registry.assumed) for r in chain),
            "guessed_count": sum(len(r.registry.guessed) for r in chain),
            "falsifications_run": sum(len(r.sprt_results) for r in chain),
            "falsifications_rejected": sum(
                sum(1 for s in r.sprt_results if s.decision == "REJECT") for r in chain
            ),
            "explanations_produced": sum(1 for r in chain if r.explanation),
            "programme_status": status,
            "compliance_status": "Article 12 satisfied" if chain else "No records yet",
        }
    }


@mcp.tool(
    name="eif_check_rules_installed",
    description=(
        "Detect whether the EIF agent rules block (<BEGIN-EIF vX.Y>, any version) is installed in this project's "
        "agent instruction files (.cursorrules, CLAUDE.md, AGENTS.md, etc.). "
        "Call this if eif_verify is producing unexpected results - missing rules are the most common cause. "
        "IMPORTANT: default paths (.cursorrules, CLAUDE.md, etc.) are resolved relative to the MCP "
        "server's process working directory. Pass absolute file_paths[] when the MCP server starts "
        "from a directory other than the project root (common in IDE integrations). "
        "Returns: installed (bool), file (path where found), version, checked_files[]."
    ),
)
def eif_check_rules_installed(file_paths: list[str] | None = None) -> dict:
    """Check if EIF rules are installed in the project."""
    default_paths = [
        ".cursorrules",
        "CLAUDE.md",
        "AGENTS.md",
        ".cursor/rules/eif.mdc",
        "system_prompt.md",
        "agent_instructions.md",
    ]
    paths_to_check = file_paths or default_paths

    for path in paths_to_check:
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            if "<BEGIN-EIF" in content:
                import re
                match = re.search(r"<BEGIN-EIF\s+(v[\d.]+)>", content)
                version = match.group(1) if match else None
                _log.info("TOOL  eif_check_rules_installed  found=%s  version=%s", path, version)
                return {"installed": True, "file": path, "version": version, "checked_files": paths_to_check}
        except (OSError, FileNotFoundError):
            continue

    _log.info("TOOL  eif_check_rules_installed  installed=False")
    return {"installed": False, "file": None, "version": None, "checked_files": paths_to_check}


# ─────────────────────────────────────────────────────────────────────────────
# RESOURCES
# ─────────────────────────────────────────────────────────────────────────────


@mcp.resource(
    uri="eif://session/{session_id}/summary",
    name="session_summary",
    description="Compact EIF session overview: session_id, decisions_recorded, assumptions_declared, known_count, assumed_count, guessed_count, falsifications_run, falsifications_rejected, explanations_produced, programme_status, compliance_status.",
    mime_type="application/json",
)
async def resource_summary(session_id: str) -> str:
    from eif.mcp_server.resources import get_summary
    return await get_summary(session_id)


@mcp.resource(
    uri="eif://session/{session_id}/registry",
    name="session_registry",
    description="Latest AssumptionRegistry - from the most recent provenance record, or from last_registry (written by eif_declare/eif_verify) when the chain is empty.",
    mime_type="application/json",
)
async def resource_registry(session_id: str) -> str:
    from eif.mcp_server.resources import get_registry
    return await get_registry(session_id)


@mcp.resource(
    uri="eif://session/{session_id}/provenance",
    name="session_provenance",
    description="Full provenance chain for the session. Use for compliance and audit.",
    mime_type="application/json",
)
async def resource_provenance(session_id: str) -> str:
    from eif.mcp_server.resources import get_provenance
    return await get_provenance(session_id)


@mcp.resource(
    uri="eif://session/{session_id}/programme",
    name="session_programme",
    description="Lakatos programme signals (full ProgrammeSignals model dump, recomputed fresh from the provenance chain): includes at least novel_prediction_rate, confirmed_prediction_rate, patch_rate, oscillation_count, status.",
    mime_type="application/json",
)
async def resource_programme(session_id: str) -> str:
    from eif.mcp_server.resources import get_programme
    return await get_programme(session_id)


@mcp.resource(
    uri="eif://session/{session_id}/calibration",
    name="session_calibration",
    description="Calibration history for the session. Enables ECE and conformal coverage computation.",
    mime_type="application/json",
)
async def resource_calibration(session_id: str) -> str:
    from eif.mcp_server.resources import get_calibration
    return await get_calibration(session_id)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def create_app() -> FastMCP:
    """Return the FastMCP app (used by tests)."""
    return mcp


@mcp.tool(
    name="eif_sycophancy_gate",
    description=(
        "ADVANCED: Detect sycophancy signals after eif_challenge and before eif_update. "
        "Use eif_verify instead - it runs this gate automatically. "
        "Parameters: session_id, turn_idx (1-based conversation turn), user_message, "
        "agent_response, falsify_probes[] (probe dicts from FALSIFY phase), "
        "calibrate_route ('ACT'/'REVISE'/'HALT' from eif_calibrate), "
        "calibrate_claims[] (optional per-claim calibration results - accepted, reserved for future S1 "
        "claim-level cross-check; not currently consumed by detection logic), "
        "challenge_result{} (optional dict from eif_challenge). "
        "Detects four signals that naive multi-turn checks miss: "
        "(S1) agreement-before-evidence - agent validates user hypothesis before EIF has supporting evidence; "
        "(S2) position drift - conclusion changed across turns without new evidence "
        "(drift_score > 0.6 AND prior routing was HALT → forces HALT; SC9: position "
        "history is process-local - cross-turn tracking resets on process restart); "
        "(S3) unfaithful CoT - agent cites evidence that FALSIFY returned CONTRADICTS or INSUFFICIENT; "
        "(S4) face-preserving framing - excessive hedging on HALT-routed turns. "
        "calibrate_route is the routing from eif_calibrate (ACT/REVISE/HALT). "
        "Returns: sycophancy_detected, adjusted_route, original_route, routing_adjustments[], signals_fired[], "
        "signals{} (per-detector detail: S1_agreement_before_evidence, S2_position_drift, "
        "S3_unfaithful_cot, S4_face_preserving - each with flagged + sub-fields), "
        "position_record{} (turn_idx, direction, routing), "
        "weak_challenge (bool - True only when challenge_result is supplied AND "
        "challenge_result.hardening_score < 0.5; False when challenge_result is omitted), "
        "hardening_score (float when challenge_result supplied, null otherwise), "
        "cost_model (when sycophancy_detected=True: bad_outcome, dollar_range_low, dollar_range_high, "
        "p_bad, expected_cost_saved, citation, domain, regulation, counterfactual_action - SC10)."
    ),
)
async def eif_sycophancy_gate(
    session_id: str,
    turn_idx: int,
    user_message: str,
    agent_response: str,
    falsify_probes: list[dict],
    calibrate_route: str,
    calibrate_claims: list[dict] | None = None,
    challenge_result: dict | None = None,
) -> dict:
    """EIF v2 Phase: SYCOPHANCY_GATE - detect sycophancy at position and framing level."""
    from eif.sycophancy.detector import SycophancyGate

    # Retrieve or create the gate for this session (session-scoped register)
    await session_store.get_session(session_id)

    # Store gate in session via a lightweight attribute trick (session is a Pydantic model)
    # Use module-level registry keyed by session_id
    gate = _sycophancy_gates.get(session_id)
    if gate is None:
        gate = SycophancyGate()
        _sycophancy_gates[session_id] = gate

    # R5-06: pass domain so SC10 cost_model uses domain-specific benchmarks
    # instead of always defaulting to "generic" inside SycophancyGate.run.
    _syco_domain = _infer_domain(user_message + " " + agent_response)
    result = gate.run(
        turn_idx=turn_idx,
        user_message=user_message,
        agent_response=agent_response,
        falsify_probes=falsify_probes,
        calibrate_route=calibrate_route,
        calibrate_claims=calibrate_claims,
        challenge_result=challenge_result,
        domain=_syco_domain,
    )

    _log.info(
        "TOOL  eif_sycophancy_gate  session=%s  turn=%d  detected=%s  route=%s→%s  adjustments=%s",
        session_id[:8], turn_idx, result.sycophancy_detected,
        calibrate_route, result.adjusted_route, result.routing_adjustments,
    )

    return result.to_dict()


# Module-level registry of SycophancyGate instances (one per session)
_sycophancy_gates: dict[str, object] = {}


# ── INPUT_GUARD MCP tool (v3.1) ───────────────────────────────────────────────

@mcp.tool(
    name="eif_input_guard",
    description=(
        "Call this on the user's input BEFORE eif_declare (or before eif_verify) "
        "when you suspect adversarial manipulation of the verification pipeline. "
        "Parameters: session_id, turn_idx (conversation turn number), user_message, "
        "prior_halts[] (list of prior HALT claim dicts - enables D2 framing injection detection), "
        "session_audit[] (optional full session history for D3 anchoring detection). "
        "Detects three injection patterns: "
        "(D1) pipeline suppression - language that attempts to bypass EIF verification; "
        "(D2) framing injection - previously HALT-routed claims restated as established facts; "
        "(D3) confidence anchoring - attribution of unverified claims to prior EIF output. "
        "Pass prior_halts from earlier in the session to enable D2 detection. "
        "IG6: result is persisted on SessionState so eif_record includes it in the audit trail. "
        "Returns: session_id, turn_idx, override_detected, framing_injections[], anchoring_attempts[], "
        "manipulation_score, degraded_claims[], warnings[], prior_overrides (pass to eif_declare), "
        "detected_at (ISO timestamp)."
    ),
)
async def eif_input_guard(
    session_id: str,
    turn_idx: int,
    user_message: str,
    prior_halts: list[dict] | None = None,
    session_audit: list[dict] | None = None,
) -> dict:
    """EIF v3.1 Phase: INPUT_GUARD - adversarial input detection."""
    from eif.input_guard.detector import detect_input_guard  # noqa: PLC0415

    result = detect_input_guard(
        user_message=user_message,
        prior_halts=prior_halts or [],
        session_audit=session_audit or [],
        session_id=session_id,
        turn_idx=turn_idx,
    )

    # IG6: persist result snapshot to session so eif_record can include it
    # in the ProvenanceRecord for a complete audit trail.
    result_dict = {
        "session_id": result.session_id,
        "turn_idx": result.turn_idx,
        "override_detected": result.override_detected,
        "framing_injections": result.framing_injections,
        "anchoring_attempts": result.anchoring_attempts,
        "manipulation_score": result.manipulation_score,
        "degraded_claims": result.degraded_claims,
        "warnings": result.warnings,
        "prior_overrides": result.prior_overrides,
        "detected_at": result.detected_at.isoformat(),
    }
    # R9-09: use explicit kwargs so update_session acquires the lock, creates a clean copy,
    # and avoids relying on in-place mutation of the session object before the lock.
    await session_store.update_session(session_id, last_input_guard=result_dict)

    return result_dict


@mcp.tool(
    name="eif_hypothesis_agenda",
    description=(
        "ADVANCED: Rank all declared claims by epistemic priority so FALSIFY tests "
        "the most decision-critical assumption first - closes S3 gap (Experimental Design). "
        "Parameters: session_id, registry{} (AssumptionRegistry dict from eif_declare), "
        "calibration_results[] (optional per-claim CalibrationResult dicts from eif_calibrate), "
        "max_probes (optional int - limits active probe budget; excess claims move to deferred). "
        "Pass the registry dict returned by eif_declare and, optionally, calibration_results "
        "from eif_calibrate. Set max_probes to limit the probe budget (e.g. max_probes=2 means "
        "only the top 2 claims are active; the rest move to deferred). "
        "Priority formula: EIG × consequence_weight × boundary_factor × uncertainty_factor. "
        "Claims near a decision threshold (ACT=0.70 or HALT=0.20) get elevated boundary_factor. "
        "HIGH-consequence GUESSED claims typically outrank LOW-consequence KNOWN claims "
        "(HA1: at equal posteriors, GUESSED HIGH scores above ASSUMED LOW by formula). "
        "FDR correction (F10, Benjamini-Hochberg) is applied automatically. "
        "Two FDR risk tiers:\n"
        "  N > 5  (6–10 claims): MEDIUM advisory - fdr_inflation_risk per item set to 'MEDIUM'; "
        "fdr_warning included with a note that multiple-testing risk is elevated.\n"
        "  N > 10 (11+ claims): HIGH advisory - fdr_warning escalated: "
        "'N claims tested - false discovery rate elevated; prioritize top-2 only.'\n"
        "Research: Chaloner & Verdinelli (1995); LAPD (arXiv:2503.02983). "
        "Returns: top_recommendation (claim text to probe first), items[] (ranked, each with "
        "priority_score, eig_score, consequence_weight, boundary_factor, fdr_alpha_adjusted, fdr_inflation_risk), "
        "deferred[] (budget-cut claims), rationale (always includes consequence and boundary_factor "
        "language per HA5), total_claims, "
        "fdr_warning (when total_claims > 5 - escalates to HIGH advisory above 10), "
        "session_id, created_at, max_probes."
    ),
)
async def eif_hypothesis_agenda(
    session_id: str,
    registry: dict,
    calibration_results: list[dict] | None = None,
    max_probes: int | None = None,
) -> dict:
    """HYPOTHESIS_AGENDA - rank claims by EIG-based priority before FALSIFY."""
    from eif.hypothesis_agenda import build_agenda  # noqa: PLC0415
    from eif.schemas import AssumptionRegistry, CalibrationResult  # noqa: PLC0415

    registry_obj = AssumptionRegistry.model_validate(registry)

    calibration_map: dict = {}
    if calibration_results:
        for cr in calibration_results:
            cal = CalibrationResult.model_validate(cr)
            calibration_map[cal.claim_text] = cal

    agenda = build_agenda(registry_obj, calibration_map=calibration_map, max_probes=max_probes)

    await session_store.update_session(session_id)  # touch to confirm session exists
    _log.info(
        "TOOL  eif_hypothesis_agenda  session=%s  total=%d  active=%d  deferred=%d  top=%r",
        session_id[:8], agenda.total_claims, len(agenda.items), len(agenda.deferred),
        agenda.top_recommendation[:60] if agenda.top_recommendation else None,
    )

    return agenda.model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# FACADE TOOLS - primary interface for most users
# These three tools cover the full discovery-to-compliance journey.
# The granular pipeline tools above are for advanced use only.
# Architecture: eif_verify orchestrates the internal pipeline internally;
# eif_get_session reads the result; eif_compliance_report exports for the
# compliance buyer. Pattern: minimal surface (3 tools) over a multi-stage pipeline.
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool(
    name="eif_extract_claims_from_decision",
    description=(
        "Call this FIRST - before eif_verify - when the user describes their agent's decision "
        "in plain text and you need to know which specific claims to verify.\n\n"
        "Takes a natural-language decision description and returns 2-4 structured claims "
        "pre-classified as KNOWN, ASSUMED, or GUESSED, ordered from highest to lowest "
        "HALT probability. Each claim includes a ready-to-use falsification_condition "
        "so you can pass the output directly to eif_verify without writing any JSON.\n\n"
        "Use this to lower the barrier to the first HALT moment: the developer describes "
        "their agent's output in one sentence; this tool surfaces the claims most likely "
        "to be fabricated.\n\n"
        "Runs locally - deterministic heuristics, no LLM call.\n\n"
        "Returns: claims[] (each with text, claim_type, consequence_of_wrong, "
        "falsification_condition, basis, halt_probability, why_this_matters), "
        "total_extracted, highest_risk_claim, next_step (ready-to-use instruction for passing to eif_verify)."
    ),
)
def eif_extract_claims_from_decision(
    decision: str,
    max_claims: int = 4,
) -> dict:
    """Facade: extract structured ClaimInput-compatible claims from plain-language decision text."""
    from eif.declare.extractor import claims_to_dict, extract_claims

    if not decision or not decision.strip():
        raise ValueError("decision cannot be empty")

    max_claims = max(2, min(max_claims, 4))
    extracted = extract_claims(decision.strip(), max_claims=max_claims)
    as_dicts = claims_to_dict(extracted)

    highest_risk = as_dicts[0] if as_dicts else None

    _log.info(
        "TOOL  eif_extract_claims_from_decision  decision=%r  extracted=%d  top_halt_prob=%s",
        decision[:50], len(as_dicts),
        f"{highest_risk['halt_probability']:.2f}" if highest_risk else "n/a",
    )

    return {
        "claims": as_dicts,
        "total_extracted": len(as_dicts),
        "highest_risk_claim": highest_risk,
        "next_step": (
            "Pass these claims to eif_verify. The falsification_condition is already set for each. "
            "Focus on claims with halt_probability >= 0.7 - those are most likely to produce a HALT."
        ),
    }


def _infer_domain(text: str) -> str:
    """Map claim/decision text to a cost_model domain key.

    Keyword heuristic - no LLM call. Falls back to "generic" when no
    domain-specific signal is present.
    """
    lower = text.lower()
    if any(w in lower for w in ("hipaa", "phi", "phii", "healthcare", "medical", "clinical", "patient data")):
        return "hipaa_compliance"
    if any(w in lower for w in ("sec filing", "disclosure", "material misstatement", "10-k", "10-q", "8-k", "proxy statement")):
        return "sec_disclosure"
    if any(w in lower for w in ("revenue", "projection", "forecast", "roi", "ebitda", "arr", "mrr", "financial model")):
        return "financial_projection"
    if any(w in lower for w in ("fda", "510k", "510(k)", "de novo", "regulatory approval", "clearance", "premarket")):
        return "regulatory_approval"
    if any(w in lower for w in ("gdpr", "data protection", "dpa", "eu privacy", "schrems", "standard contractual")):
        return "data_privacy_gdpr"
    return "generic"


# Self-preference detection threshold.
# arXiv:2509.00462 (Xu et al. 2025): large models prefer self-generated content 67–82%.
# Overlap threshold: ≥35% token overlap between claim and any prior assistant turn
# is treated as evidence of self-generation. This is conservative - it fires on
# paraphrase-level similarity, not just exact repeat.
_SELF_PREFERENCE_OVERLAP_THRESHOLD = 0.35

_SELF_PREFERENCE_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "and", "or", "but", "if", "that", "this", "it",
    "its", "their", "our", "your", "as", "not", "than", "more", "also",
    "we", "i", "you", "they", "he", "she", "which", "who", "what", "when",
})


def _compute_self_preference_risk(
    claim_text: str,
    conversation_turns: list[dict],
) -> tuple[bool, float]:
    """Detect whether a claim likely originated in a prior assistant turn.

    Returns (is_at_risk, overlap_score) where overlap_score ∈ [0, 1].

    Algorithm:
      1. Collect all content from assistant turns.
      2. Tokenise claim and assistant content, removing stop-words.
      3. Compute Jaccard similarity (intersection / union) between claim tokens
         and the combined assistant token set.
      4. Flag as at-risk if Jaccard ≥ _SELF_PREFERENCE_OVERLAP_THRESHOLD.

    This is intentionally conservative (Jaccard, not cosine). It fires on
    paraphrase-level overlap without requiring embedding computation, keeping
    the implementation deterministic and zero-LLM.

    Research basis:
      Xu et al. (arXiv:2509.00462, 2025): self-recognition → self-preference.
      Panickssery et al. (NeurIPS 2024): LLM evaluators recognise and favour
      their own generations.
    """
    if not conversation_turns:
        return False, 0.0

    assistant_content = " ".join(
        t.get("content", "")
        for t in conversation_turns
        if t.get("role") == "assistant"
    )
    if not assistant_content.strip():
        return False, 0.0

    def _tokenise(text: str) -> set[str]:
        return {
            t for t in re.split(r"\W+", text.lower())
            if t and len(t) > 2 and t not in _SELF_PREFERENCE_STOP_WORDS
        }

    claim_tokens = _tokenise(claim_text)
    assistant_tokens = _tokenise(assistant_content)

    if not claim_tokens or not assistant_tokens:
        return False, 0.0

    intersection = claim_tokens & assistant_tokens
    union = claim_tokens | assistant_tokens
    overlap = len(intersection) / len(union)

    return overlap >= _SELF_PREFERENCE_OVERLAP_THRESHOLD, round(overlap, 3)


# ─────────────────────────────────────────────────────────────────────────────
# Instability probe (S0 - gap: instability_probe)
# ─────────────────────────────────────────────────────────────────────────────
# Detects "stochastic fabrication": the same claim topic produces different
# numeric values across repeated eif_verify calls for the same session.
# This is purely deterministic - no LLM needed. Uses regex to extract numbers
# and a topic fingerprint (claim text with all numbers → "#") as the key.
#
# Research basis: the user's personal experience - "my mistrust made me ask
# again and it pulled different information." This is exactly the failure mode
# that EIF should surface: agent instability on quantitative claims.

# Session-level store: session_id → topic_fingerprint → [values seen per call]
_session_numeric_claims: dict[str, dict[str, list[float]]] = {}

# Minimum absolute relative difference to flag as instability
_INSTABILITY_MIN_REL_DIFF = 0.05  # 5% relative change is enough to flag

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?%?")


def _extract_numeric_claims(claim_text: str) -> tuple[str, list[float]]:
    """Return (topic_fingerprint, [numeric_values]) for a claim string.

    topic_fingerprint: the claim with all numbers replaced by '#'.
    numeric_values: every number found in the claim (as float).
    Percentages like '73%' are stored as 73.0 (the '%' is part of the fingerprint).
    """
    nums: list[float] = []
    fingerprint = claim_text

    def _replace(m: re.Match) -> str:
        raw = m.group(0)
        digits = raw.rstrip("%").replace(",", "")
        try:
            nums.append(float(digits))
        except ValueError:
            pass
        return "#" if not raw.endswith("%") else "#%"

    fingerprint = _NUMBER_RE.sub(_replace, fingerprint)
    return fingerprint.lower().strip(), nums


def _check_instability(
    session_id: str, claims: list
) -> list[dict]:
    """Check each claim against prior calls in this session for numeric variance.

    Returns a list of instability signal dicts - one per conflicting claim.
    Side-effect: updates _session_numeric_claims for this session.
    """
    signals: list[dict] = []
    session_store_local = _session_numeric_claims.setdefault(session_id, {})

    for claim in claims:
        text = getattr(claim, "text", "") if not isinstance(claim, dict) else claim.get("text", "")
        fingerprint, values = _extract_numeric_claims(text)

        if not values or not fingerprint:
            continue

        prior_values = session_store_local.get(fingerprint)
        if prior_values is not None:
            # Compare first value from prior call vs first value from this call
            prior = prior_values[0]
            current = values[0]
            if prior == 0:
                rel_diff = abs(current - prior)
            else:
                rel_diff = abs(current - prior) / abs(prior)
            if rel_diff >= _INSTABILITY_MIN_REL_DIFF:
                signals.append({
                    "claim": text[:200],
                    "topic_fingerprint": fingerprint[:200],
                    "prior_value": prior,
                    "current_value": current,
                    "relative_diff_pct": round(rel_diff * 100, 1),
                    "signal": "INSTABILITY_RISK",
                    "note": (
                        f"Same claim topic produced {prior} in a prior call and {current} in this call "
                        f"({round(rel_diff * 100, 1)}% difference). "
                        "This is a stochastic fabrication signal - the model is not drawing from a stable "
                        "factual source. Verify with an authoritative external source before acting."
                    ),
                })
        # Record this call's values (overwrite - track most recent)
        session_store_local[fingerprint] = values

    return signals


# ─────────────────────────────────────────────────────────────────────────────
# HALT card formatter (S3 - gap: halt_screen_formatting)
# ─────────────────────────────────────────────────────────────────────────────

def _format_halt_card(entry: dict) -> str:
    """Return a markdown HALT card ready for display in Cursor / Claude Code.

    The card answers three questions in under 30 seconds:
      1. What was claimed?
      2. Why was it blocked and what evidence contradicts it?
      3. What is the dollar consequence if acted on?

    This is the S3 aha-moment surface. Every field must be readable by a
    developer who has never used EIF before - no SPRT, no CEP, no pipeline jargon.
    """
    claim = entry.get("claim", "")[:160]
    reason = entry.get("reason", "")
    evidence = entry.get("evidence_summary", "No evidence summary available.")
    source = entry.get("evidence_source", "")
    posterior = entry.get("posterior")
    cost = entry.get("cost_impact", {})
    sp_note = entry.get("self_preference_note", "")

    # Human-readable reason line
    reason_map = {
        "EVIDENCE_CONTRADICTS": "Contradicted by independent evidence",
        "EVIDENCE_INSUFFICIENT": "No independent evidence found - claim has no basis",
        "GUESSED_NO_SUPPORT": "Claim is GUESSED (specific assertion, no source) with no supporting evidence",
        "HARKING": "Hypothesis stated after results are known",
    }
    for key, label in reason_map.items():
        if key in reason:
            reason_label = label
            break
    else:
        if "SYCOPHANCY" in reason:
            reason_label = "Sycophantic drift - position changed without new evidence"
        elif "HIGH_RISK" in reason:
            reason_label = "High-risk assumption - evidence present but not independently verified"
        else:
            reason_label = reason

    lines = [
        "### ⚠ HALT",
        f"**Claim:** {claim}",
        "",
        f"**Why blocked:** {reason_label}",
        f"**Evidence:** {evidence}",
    ]
    if source:
        lines.append(f"**Source:** `{source}`")
    if posterior is not None:
        # Pipeline posteriors encode P(claim is true). Show both numbers so auditors
        # can read either direction: belief the claim holds, and residual doubt.
        belief_pct = round(posterior * 100)
        doubt_pct = round((1 - posterior) * 100)
        lines.append(f"**Belief claim holds:** {belief_pct}% | **Residual doubt:** {doubt_pct}%")
    if sp_note:
        lines.append(f"**Self-preference note:** {sp_note}")
    if cost:
        expected = cost.get("expected_cost_saved") or (
            (cost.get("dollar_range_low", 0) + cost.get("dollar_range_high", 0)) / 2
            * cost.get("p_bad", 0.5)
        )
        hi = cost.get("dollar_range_high", 0)
        citation = cost.get("citation", "")
        regulation = cost.get("regulation", "")
        lines += [
            "",
            f"**Cost consequence if acted on:** ~${expected:,.0f} expected | up to ${hi:,.0f} maximum",
        ]
        if citation:
            lines.append(f"**Source:** {citation}")
        if regulation:
            lines.append(f"**Regulation:** {regulation}")
    lines += [
        "",
        "_Correct or provide supporting evidence before proceeding._",
    ]
    return "\n".join(lines)



# Session HALT counter + compliance email trigger
# ─────────────────────────────────────────────────────────────────────────────

# In-memory halt counter per session. Survives the process lifetime.
# For multi-process deployments, persist this to the cost ledger instead.
_session_halt_counts: dict[str, int] = {}

# Threshold: surface the compliance email template after this many total HALTs
_COMPLIANCE_EMAIL_HALT_THRESHOLD = 3


def _generate_compliance_email_template(
    session_id: str,
    total_halts: int,
    cost_summary: dict,
    articles_covered: list[str] | None = None,
) -> str:
    """Return a ready-to-forward compliance email template.

    Written in compliance language, not developer language. The recipient is
    a compliance officer or auditor - not the developer. No jargon.

    S6 constraint: "The email template is ready to send as-is. No customisation
    required before forwarding."
    """
    if articles_covered is None:
        articles_covered = ["Art. 9 - Risk Management", "Art. 12 - Record-keeping and Provenance"]

    total_cost = cost_summary.get("total_expected", 0.0)
    articles_str = ", ".join(articles_covered) if articles_covered else "Art. 9, Art. 12"

    return f"""Subject: AI agent audit - {total_halts} unverified claims blocked (EIF session {session_id[:8]})

Hi,

Our AI agent pipeline ran {total_halts} decision{'s' if total_halts != 1 else ''} \
that were flagged by EIF (Epistemic Integrity Framework) as containing claims \
the model asserted with high confidence that could not be verified against \
independent evidence.

Summary:
  - Claims blocked (HALT): {total_halts}
  - Estimated cost consequence if acted on: ${total_cost:,.0f}
  - EU AI Act articles documented: {articles_str}
  - Session reference: {session_id}

A full compliance report can be generated with \
eif_compliance_report(session_id="{session_id}") and attached to this email. \
It maps each blocked claim to the relevant EU AI Act article and includes \
the contradicting evidence and its source.

Before sending, each flagged claim should be reviewed by a human; once that \
review has happened, this email and the attached report can serve as part of \
your Art. 14 human oversight record for these decisions.

For background on the compliance mapping, see:
https://github.com/leocelis/eif/blob/main/docs/compliance.md

Please retain for your audit file.

---
Generated automatically by EIF Engine after {_COMPLIANCE_EMAIL_HALT_THRESHOLD}+ HALT events.
To generate the full compliance report: call eif_compliance_report(session_id="{session_id}")"""


@mcp.tool(
    name="eif_verify",
    description=(
        "Call this before any agent decision that acts on a confident-but-wrong output - "
        "claims about costs, compliance requirements, API behavior, causal relationships, "
        "or statistics the model stated with high confidence. "
        "Parameters: session_id (REQUIRED - obtain it from eif_new_session; never invent an id, "
        "an unknown session_id fails with 'session not found'), decision (agent's output text), "
        "claims[] (ClaimInput dicts - each needs text and claim_type, where claim_type is exactly "
        "one of KNOWN, ASSUMED, or GUESSED; no other value validates. Prefer building claims with "
        "eif_extract_claims_from_decision, which sets these fields correctly), "
        "conversation_turns[] (optional prior turns for sycophancy/self-preference detection), "
        "model_name (optional str - model that produced the claims; default 'unknown'), "
        "host_tool_outputs[] (optional list of P0 host-tool result dicts - each with claim_text, "
        "verdict (SUPPORTS/CONTRADICTS/INSUFFICIENT), posterior, evidence_source, and optionally "
        "raw_result; when present, treated as highest-priority P0 tier evidence).\n\n"
        "Architecture note: eif_verify is an integrated façade. It runs an evidence-first pipeline "
        "internally (DECLARE → evidence probes → sycophancy gate → instability check) and does NOT "
        "call the granular tools (eif_causal_gate, eif_calibrate, eif_challenge, eif_update, eif_explain, "
        "eif_record, eif_hypothesis_agenda). Use the granular tools for step-by-step control; use "
        "eif_verify for a single call that covers the critical HALT/ACT decision. "
        "Internally invokes the same core logic modules (Bayesian posterior, evidence collection, "
        "sycophancy detection, cost modeling) as the granular tools - packaged as a single MCP "
        "response instead of N separate tool calls, not as a lightweight stub.\n\n"
        "Catches failure patterns that naive hallucination checks miss:\n"
        "1. Sycophantic drift - model changed its answer under social pressure without new evidence. "
        "Naive single-turn checks miss this; this tool detects drift across the conversation.\n"
        "2. Self-preference bias + circular self-validation - a 2025 controlled study "
        "(arXiv:2509.00462, 2,245 resumes, 7 LLMs) found large models prefer their own generated "
        "content 67–82% of the time regardless of actual quality. GPT-4o: 82%. "
        "This is the structural cause of the Mata v. Avianca failure: ChatGPT confirmed its own "
        "fabricated cases because self-generated content carries the model's stylistic fingerprint. "
        "This tool detects claims with high overlap with prior assistant turns, flags them as "
        "self_preference_risk, and blocks parametric self-validation for those claims - "
        "ensuring the model that generated a claim cannot also verify it.\n"
        "3. Causal errors - model presents a correlation as a cause, or inverts the direction "
        "of causation. Catches the same pattern as the corpus REVERSED verdict (CARET/ATBC clinical trial).\n\n"
        "Returns PASS or HALT. HALT includes: the specific failure type, the contradicting evidence "
        "with source citation, and a cost impact estimate sourced from domain benchmarks "
        "(HHS OCR enforcement data, SEC enforcement actions, Gartner 2024, HIPAA Tier 3 penalties).\n\n"
        "Verification logic runs on your server. Evidence collection may make outbound calls: "
        "P3 (DDGS web search) is used when available; P4 parametric probes are not fired by this tool. "
        "No third-party EIF scoring service receives your data. For P3/P4, evidence queries are "
        "derived from claim text - claim-derived probe prompts may reach OpenAI when OPENAI_API_KEY "
        "is set. Raw agent responses and full claim payloads are not forwarded. Call once per claim set.\n\n"
        "Returns: verdict (PASS/HALT), halted_claims[], halt_cards[] (formatted markdown cards "
        "suitable for display), evidence_trails[] (each entry: claim, verdict, posterior, "
        "probe_tier, evidence_summary, evidence_source, retrieved_at, self_preference_risk, "
        "self_preference_overlap; optional keys: metric_quality (F17 - present when evidence was "
        "degraded parametric fallback), self_preference_note (present when self_preference_risk=True)), "
        "retrieval_trace[] (per-step timing), "
        "instability_signals[] (stochastic fabrication indicators - each: claim, topic_fingerprint, "
        "prior_value, current_value, relative_diff_pct, signal='INSTABILITY_RISK', note), "
        "sycophancy_detected (bool), "
        "self_preference_flagged[] (claims blocked from self-validation), "
        "cumulative_cost_protected (dict: total_expected, halt_count, session_id - "
        "persisted per session in ~/.eif/cost_ledger.json; total_expected is cumulative dollar value protected), "
        "registry_summary (known/assumed/guessed/high_risk_assumed/harking_detected counts), "
        "stale_evidence_warnings[] (claims with evidence older than EVIDENCE_STALENESS_DAYS=30 days), "
        "compliance_email_template (populated when session HALT count crosses threshold, null otherwise), "
        "next_step (ready-to-use instruction for addressing any HALT)."
    ),
)
async def eif_verify(
    session_id: str,
    decision: str,
    claims: list[dict],
    conversation_turns: list[dict] | None = None,
    model_name: str = "unknown",
    host_tool_outputs: list[dict] | None = None,
) -> dict:
    """Facade: run the full EIF pipeline and return PASS/HALT with evidence trail.

    claims: list of {"text": str, "claim_type": "KNOWN"|"ASSUMED"|"GUESSED",
                     "falsification_condition": str (optional)}
    conversation_turns: list of {"role": "user"|"assistant", "content": str}
    host_tool_outputs: list of pre-collected tool results from the host agent,
        each as {"tool_name": str, "query": str, "result": str, "data_scope": str}.
        These are fed into P0 as passive evidence (the host already ran its tools).
        For active delegation where EIF calls the tool itself, register a
        HostToolRegistry directly in the Python integration layer.
    """
    from eif.calibrate.bayesian import compute_posterior
    from eif.calibrate.trust import tier_confidence_likelihood
    from eif.cost_model.cost_ledger import get_ledger
    from eif.declare.harking_guard import detect_harking
    from eif.declare.registry import build_registry
    from eif.falsify.evidence_collector import (
        HostTool,
        HostToolRegistry,
        collect_evidence,
    )
    from eif.schemas import ClaimInput
    from eif.sycophancy.cost_model import build_cost_model

    # Retrieval trace - records each pipeline step with elapsed time.
    # Included in the response so the developer can see what happened, not a blank wait.
    # Show the work, not a spinner.
    _t0 = time.perf_counter()
    retrieval_trace: list[dict] = []

    def _trace(label: str, detail: str = "") -> None:
        retrieval_trace.append({
            "step": len(retrieval_trace) + 1,
            "label": label,
            "detail": detail,
            "elapsed_ms": round((time.perf_counter() - _t0) * 1000, 1),
        })

    claim_objects = [ClaimInput.model_validate(c) for c in claims]
    registry, stale_warnings = build_registry(session_id, decision, claim_objects)
    registry = detect_harking(registry)

    # R5-02: persist registry to session immediately after building so eif_record
    # (if called later in the same session) always gets the real classified registry.
    try:
        await session_store.update_session(session_id, last_registry=registry.model_dump())
    except Exception as _rv_exc:  # noqa: BLE001
        _log.warning("eif_verify: registry persist failed (non-fatal): %s", _rv_exc)

    _trace(
        "Claims classified",
        f"{len(registry.known)} KNOWN · {len(registry.assumed)} ASSUMED · "
        f"{len(registry.guessed)} GUESSED"
        + (" · HARKING detected" if registry.harking_flag else ""),
    )

    await session_store.update_session(session_id)

    # Build a HostToolRegistry from pre-collected host tool outputs (P0 passive mode).
    # Each entry in host_tool_outputs is a captured result the MCP client already
    # retrieved - we wrap it in a callable so collect_evidence's P0 tier can use it.
    mcp_tool_registry: HostToolRegistry | None = None
    if host_tool_outputs:
        tools = []
        for entry in host_tool_outputs:
            tool_name = entry.get("tool_name", "host_tool")
            result_text = entry.get("result", "")
            query_used = entry.get("query", "")
            data_scope = entry.get("data_scope", "INTERNAL")
            # Derive capability_keywords from the query that produced this result
            kw_terms = [t for t in re.split(r"\W+", query_used.lower()) if len(t) > 3][:8]
            # Wrap the pre-collected result as a callable - ignores the new query,
            # returns the stored result (it was already collected for this claim set).
            stored = result_text

            def _make_fn(text: str):  # closure over stored result
                def _fn(_query: str) -> str:
                    return text
                return _fn

            tools.append(HostTool(
                name=tool_name,
                description=f"Pre-collected result from {tool_name}",
                capability_keywords=kw_terms,
                fn=_make_fn(stored),
                data_scope=data_scope,
            ))
        mcp_tool_registry = HostToolRegistry(tools)

    # Evidence collection: probe every ASSUMED and GUESSED claim via the
    # five-tier strategy (P0 host tools → P2 coordinator outputs → P1 code execution →
    # P3 DDGS web search → P4 parametric fallback). P2 runs before P1 (intent C3/C9).
    # Private data claims are blocked from web search if no host tool is configured (intent C10).
    halted_claims: list[dict] = []
    evidence_trails: list[dict] = []

    for claim_obj in list(registry.assumed) + list(registry.guessed):
        claim_text = claim_obj.text
        falsification_cond = getattr(claim_obj, "falsification_condition", None) or ""

        # Self-preference risk detection (arXiv:2509.00462, Xu et al. 2025):
        # if the claim has high token overlap with prior assistant turns, the model
        # likely generated it - and would prefer it 67–82% of the time regardless
        # of actual evidence quality. Block P4 for self-referential claims.
        sp_risk, sp_overlap = _compute_self_preference_risk(
            claim_text, conversation_turns or []
        )

        _n_probing = len(evidence_trails) + 1
        _n_total = len(list(registry.assumed) + list(registry.guessed))
        _trace(
            f"Probing claim {_n_probing}/{_n_total}",
            f"{claim_text[:80]}{'…' if len(claim_text) > 80 else ''}",
        )

        # C5: SPRT CONTINUE loop - when evidence is INSUFFICIENT, issue up to 2
        # follow-up queries with progressively narrowed search terms.
        # Total attempts: 3 (initial + 2 follow-up). Intent: eif_evidence_collection
        # §C5; research: FIRE arXiv:2411.00784 (iterative retrieval on CONTINUE).
        _max_attempts = 3
        evidence = None
        for _attempt in range(_max_attempts):
            _fc_for_attempt = falsification_cond
            if _attempt == 1:
                # First follow-up: add "empirical evidence" specificity marker
                _fc_for_attempt = (
                    f"{falsification_cond} empirical evidence peer-reviewed"
                    if falsification_cond else f"{claim_text} empirical data"
                )
            elif _attempt == 2:
                # Second follow-up: narrow to primary domain term
                _domain_terms = [
                    w for w in claim_text.lower().split()
                    if len(w) > 5 and w.isalpha()
                ][:3]
                _fc_for_attempt = (
                    f"{' '.join(_domain_terms)} systematic review statistics"
                    if _domain_terms else falsification_cond
                )

            evidence = collect_evidence(
                claim_text,
                falsification_condition=_fc_for_attempt,
                host_tool_registry=mcp_tool_registry,
                self_preference_risk=sp_risk,
            )
            if evidence.verdict != "INSUFFICIENT" or _attempt == _max_attempts - 1:
                break
            _trace(
                f"CONTINUE loop attempt {_attempt + 1}/{_max_attempts}",
                "INSUFFICIENT - retrying with narrower query",
            )

        evidence_supports = evidence.verdict == "SUPPORTS"
        # TW1 (eif_v5_evidence_trust_weighting): derive a tier- and confidence-aware
        # likelihood instead of the flat 0.8/0.2 default. A single uncorroborated P3
        # web match (conf ~0.65) now yields posterior < ACT (0.70), while P0/P1 and
        # corroborated (>= 2 independent sources) web evidence can reach ACT.
        _likelihood = tier_confidence_likelihood(
            evidence.probe_tier, evidence.confidence, evidence_supports,
            getattr(evidence, "corroborated", False),
        )
        posterior, _ = compute_posterior(0.5, evidence_supports, likelihood_estimate=_likelihood)
        _trace(
            f"Evidence result {_n_probing}/{_n_total}",
            f"{evidence.probe_tier} → {evidence.verdict} "
            f"(posterior {round(posterior, 2)})",
        )

        # TW3 (eif_v5_evidence_trust_weighting): HIGH-consequence corroboration gate.
        # A single uncorroborated web SUPPORTS for a HIGH-consequence claim must not
        # drive an ACT - it is the PoisonedRAG (arXiv:2402.07867) attack surface.
        # Scoped to HIGH-consequence only to bound the false-HALT tax on routine claims.
        _high_consequence = getattr(claim_obj, "consequence_of_wrong", "MEDIUM") == "HIGH"
        _uncorroborated_web = (
            evidence.probe_tier == "P3_WEB_SEARCH"
            and not getattr(evidence, "corroborated", False)
        )
        _weak_high = _high_consequence and _uncorroborated_web and evidence.verdict == "SUPPORTS"

        # Trigger HALT when evidence contradicts, is insufficient for a GUESSED
        # claim (which has no declared basis), posterior falls below the threshold
        # used throughout the pipeline, or the HIGH-consequence corroboration gate fires.
        is_guessed = claim_obj in registry.guessed
        should_halt = (
            evidence.verdict == "CONTRADICTS"
            or posterior < THRESHOLD_HALT
            or (is_guessed and evidence.verdict == "INSUFFICIENT")
            or _weak_high
        )

        trail_entry: dict = {
            "claim": claim_text,
            "verdict": evidence.verdict,
            "posterior": round(posterior, 3),
            "probe_tier": evidence.probe_tier,
            "evidence_summary": evidence.evidence_summary,
            "evidence_source": evidence.evidence_source,
            # C7: surface retrieved_at for DeepTRACE temporal currency
            "retrieved_at": evidence.retrieved_at.isoformat() if evidence.retrieved_at else None,
            "self_preference_risk": sp_risk,
            "self_preference_overlap": sp_overlap,
            # TW4/TW5 (eif_v5_evidence_trust_weighting): web-corroboration signals.
            "independent_source_count": getattr(evidence, "independent_source_count", 0),
            "corroborated": getattr(evidence, "corroborated", False),
        }
        # F17: surface metric_quality in the evidence trail so clients can see degraded evidence
        if evidence.metric_quality is not None:
            trail_entry["metric_quality"] = evidence.metric_quality
        if sp_risk:
            trail_entry["self_preference_note"] = (
                f"Claim has {sp_overlap:.0%} token overlap with prior assistant turns. "
                "P4 parametric self-validation blocked (arXiv:2509.00462: 67–82% self-preference bias). "
                "Evidence from independent tiers only."
            )
        evidence_trails.append(trail_entry)

        if should_halt:
            domain = _infer_domain(claim_text)
            cost = build_cost_model(domain)
            # TW3: when the HIGH-consequence corroboration gate is the trigger, use a
            # dedicated reason. Otherwise keep the existing EVIDENCE_*/GUESSED reasons.
            if _weak_high and evidence.verdict != "CONTRADICTS":
                _halt_reason = (
                    "WEAK_EVIDENCE_HIGH_CONSEQUENCE - single uncorroborated web source "
                    "for a HIGH-consequence claim; require P0/P1 or >= 2 independent sources"
                )
            elif is_guessed:
                _halt_reason = "GUESSED_NO_SUPPORT"
            else:
                _halt_reason = f"EVIDENCE_{evidence.verdict}"
            halt_entry: dict = {
                "claim": claim_text,
                "reason": _halt_reason,
                "evidence_summary": evidence.evidence_summary,
                "evidence_source": evidence.evidence_source,
                "posterior": round(posterior, 3),
                "cost_impact": cost.to_dict(),
            }
            if sp_risk:
                halt_entry["self_preference_risk"] = True
                halt_entry["self_preference_overlap"] = sp_overlap
                halt_entry["self_preference_note"] = (
                    "Claim originated in a prior assistant turn (self-generated). "
                    "P4 self-validation was blocked. "
                    "Independent evidence required before acting on this claim."
                )
            halted_claims.append(halt_entry)
        elif claim_obj in registry.high_risk_assumed:
            # Not halted but high-risk - surface for human review without blocking
            halted_claims.append({
                "claim": claim_text,
                "reason": "HIGH_RISK_ASSUMED - evidence present but verify before acting",
                "advisory": True,
                "evidence_summary": evidence.evidence_summary,
                "evidence_source": evidence.evidence_source,
                "posterior": round(posterior, 3),
                "self_preference_risk": sp_risk,
            })

    # F17: collect metric_quality flags from all evidence results and persist in session state.
    # eif_record will read these and populate ProvenanceRecord.metric_quality_flags.
    _mq_flags: list[str] = list({
        t["metric_quality"]
        for t in evidence_trails
        if t.get("metric_quality") is not None
    })
    if _mq_flags:
        await session_store.update_session(session_id, metric_quality_flags=_mq_flags)

    # TW9 (eif_v5_evidence_trust_weighting): expose the evidence quality mix behind
    # the verdict - a per-tier count and the % of probed claims backed by an
    # authoritative host tool (P0). Lets callers audit what evidence drove a PASS.
    evidence_tier_mix: dict[str, int] = {}
    for _t in evidence_trails:
        _tier = _t.get("probe_tier", "UNKNOWN")
        evidence_tier_mix[_tier] = evidence_tier_mix.get(_tier, 0) + 1
    _p0_count = sum(1 for _t in evidence_trails if _t.get("probe_tier") == "P0_HOST_TOOL")
    p0_coverage_pct = round(100 * _p0_count / max(1, len(evidence_trails)), 1)
    _trace(
        "Evidence tier mix",
        ", ".join(f"{k}:{v}" for k, v in sorted(evidence_tier_mix.items()))
        + f" · P0 coverage {p0_coverage_pct}%"
        if evidence_tier_mix else "no claims probed",
    )

    # Sycophancy gate - only runs if conversation context is provided
    syco_result = None
    if conversation_turns:
        from eif.sycophancy.detector import SycophancyGate
        gate = _sycophancy_gates.get(session_id)
        if gate is None:
            gate = SycophancyGate()
            _sycophancy_gates[session_id] = gate

        last_user = next(
            (t["content"] for t in reversed(conversation_turns) if t.get("role") == "user"), ""
        )
        last_agent = next(
            (t["content"] for t in reversed(conversation_turns) if t.get("role") == "assistant"), ""
        )
        # Derive the real calibrate_route from evidence results so far - 
        # hardcoding "ACT" prevents SC6 (force HALT on drift_score > 0.6) from
        # ever firing when eif_verify is used as the entry point.
        _current_route = "HALT" if any(not e.get("advisory") for e in halted_claims) else "ACT"
        # R4-ME-03: build falsify_probes from evidence_trails so SC1 (agreement-before-evidence)
        # and SC3 (unfaithful CoT vs CONTRADICTS/INSUFFICIENT) can fire as intended.
        # R5-04: evidence trails store the tier under "probe_tier" (see trail_entry construction);
        # "tier" is absent. Use probe_tier with fallback to "tier" for forward-compat.
        _falsify_probes = [
            {
                "claim_text": t.get("claim", ""),
                "verdict": t.get("verdict", "UNKNOWN"),
                "tier": t.get("probe_tier") or t.get("tier", ""),
            }
            for t in evidence_trails
            if t.get("claim")
        ]
        # R5-06: pass domain so SC10 cost_model uses domain-specific benchmarks.
        syco_result = gate.run(
            turn_idx=len(conversation_turns),
            user_message=last_user,
            agent_response=last_agent,
            falsify_probes=_falsify_probes,
            calibrate_route=_current_route,
            domain=_infer_domain(decision),
        )

    sycophancy_fired = syco_result.sycophancy_detected if syco_result else False
    _trace(
        "Sycophancy gate",
        "FIRED" if sycophancy_fired else ("PASS" if conversation_turns else "SKIPPED - no conversation context"),
    )
    if sycophancy_fired and syco_result:
        domain = _infer_domain(decision)
        cost = build_cost_model(domain)
        syco_dict = syco_result.to_dict()
        halted_claims.append({
            "claim": decision[:200],
            "reason": f"SYCOPHANCY - {syco_result.routing_adjustments}",
            "signals": syco_dict.get("signals_fired", []),
            "cost_impact": cost.to_dict(),
        })

    if registry.harking_flag:
        halted_claims.append({"claim": decision[:200], "reason": "HARKING - hypothesis stated after results known"})

    # ── Instability probe (S0 gap: instability_probe) ────────────────────────
    # Runs after evidence collection so we only compare fully-processed claims.
    # This detects numeric variance across repeated calls for the same session.
    instability_signals = _check_instability(session_id, claim_objects)
    _trace(
        "Instability probe",
        f"{len(instability_signals)} variance signal(s) detected" if instability_signals else "CLEAN",
    )

    # Advisory entries (HIGH_RISK_ASSUMED review flags) are surfaced in
    # halted_claims but do not block: only true HALT entries drive the verdict.
    halt = any(not e.get("advisory") for e in halted_claims)
    verdict = "HALT" if halt else "PASS"
    _trace(
        "Verdict",
        f"{verdict} - {len(halted_claims)} claim(s) halted · "
        f"total {round((time.perf_counter() - _t0) * 1000)} ms",
    )

    # ── HALT cards (S3 gap: halt_screen_formatting) ───────────────────────────
    # Format each halted claim as a ready-to-display markdown card. The card
    # is added alongside the raw halted_claims dict so clients that prefer
    # structured data can still use it.
    halt_cards: list[str] = [_format_halt_card(entry) for entry in halted_claims]

    # ── Cumulative cost ledger ────────────────────────────────────────────────
    # Record every HALT's expected cost to the persistent ledger. Returns the
    # running total for this session so the response always includes the
    # lifetime "cost protected" figure.
    ledger = get_ledger()
    for entry in halted_claims:
        if entry.get("advisory"):
            continue
        cost_dict = entry.get("cost_impact", {})
        expected = float(cost_dict.get("expected_cost_saved", 0.0))
        if expected > 0:
            ledger.record_halt(key=session_id, expected_cost=expected)

    cost_summary = ledger.get_summary(session_id)

    # ── Compliance email trigger (S6 gap: auto_email_template_trigger) ────────
    # Track cumulative HALT count across all eif_verify calls for this session.
    # When it reaches the threshold, surface the compliance email template once.
    prior_count = _session_halt_counts.get(session_id, 0)
    new_count = prior_count + len([e for e in halted_claims if "HIGH_RISK" not in e.get("reason", "")])
    _session_halt_counts[session_id] = new_count

    compliance_email_template: str | None = None
    if new_count >= _COMPLIANCE_EMAIL_HALT_THRESHOLD and prior_count < _COMPLIANCE_EMAIL_HALT_THRESHOLD:
        # First time crossing the threshold this session - surface the template
        compliance_email_template = _generate_compliance_email_template(
            session_id=session_id,
            total_halts=new_count,
            cost_summary=cost_summary,
        )

    self_preference_flagged = [
        t["claim"] for t in evidence_trails if t.get("self_preference_risk")
    ]

    _log.info(
        "TOOL  eif_verify  session=%s  decision=%r  verdict=%s  evidence_probed=%d  syco=%s  sp_flagged=%d  halts_total=%d  cost_total=%.2f  instability=%d",
        session_id[:8], decision[:40], verdict,
        len(list(registry.assumed) + list(registry.guessed)),
        sycophancy_fired,
        len(self_preference_flagged),
        new_count,
        cost_summary["total_expected"],
        len(instability_signals),
    )

    return {
        "verdict": verdict,
        "halted_claims": halted_claims,
        "halt_cards": halt_cards,
        "evidence_trails": evidence_trails,
        "retrieval_trace": retrieval_trace,
        "registry_summary": {
            "known": len(registry.known),
            "assumed": len(registry.assumed),
            "guessed": len(registry.guessed),
            "high_risk_assumed": len(registry.high_risk_assumed),
            "harking_detected": registry.harking_flag,
        },
        "sycophancy_detected": sycophancy_fired,
        "self_preference_flagged": self_preference_flagged,
        "instability_signals": instability_signals,
        # TW9: evidence quality mix behind the verdict.
        "evidence_tier_mix": evidence_tier_mix,
        "p0_coverage_pct": p0_coverage_pct,
        "cumulative_cost_protected": {
            "total_expected": cost_summary["total_expected"],
            "halt_count": cost_summary["halt_count"],
            "session_id": session_id,
        },
        "compliance_email_template": compliance_email_template,
        "stale_evidence_warnings": stale_warnings,
        "next_step": (
            "Review halt_cards - each is a formatted summary of the blocked claim, "
            "the contradicting evidence, and the cost consequence. Correct or provide "
            "supporting evidence before proceeding."
            + (" Call eif_compliance_report to generate the full EU AI Act compliance report."
               if new_count >= _COMPLIANCE_EMAIL_HALT_THRESHOLD else "")
            if halt else
            "All claims pass. Call eif_record to store the provenance trail for audit."
        ),
    }


@mcp.tool(
    name="eif_demo",
    description=(
        "Run a pre-built demo that shows exactly what EIF does - with zero API calls and "
        "instant results. Use this in a first session to see a real HALT before testing "
        "your own decisions.\n\n"
        "The demo uses a real gaming-agent scenario: an AI agent recommended a 10-article "
        "series based on fabricated IGDB metrics (claimed 5,000+ hype followers; actual: 47). "
        "EIF HALT-routes both claims with evidence and cost impact.\n\n"
        "Returns: a complete eif_verify-shaped response. Top-level keys: "
        "is_demo (true), demo_note (scenario description), verdict (HALT), "
        "halted_claims[] (claim/reason/posterior/cost_impact per blocked claim), "
        "halt_cards[] (formatted markdown cards), evidence_trails[] (per-claim probe detail), "
        "retrieval_trace[] (step-by-step pipeline trace), "
        "registry_summary (KNOWN/ASSUMED/GUESSED counts), "
        "sycophancy_detected, self_preference_flagged, instability_signals, "
        "compliance_email_template, cumulative_cost_protected (nested dict), "
        "stale_evidence_warnings[], next_step.\n\n"
        "After seeing this, call eif_verify with your own decision to test live claims."
    ),
)
async def eif_demo() -> dict:
    """Pre-built demo: gaming agent scenario, guaranteed HALT, zero latency.

    All dollar figures in the demo cards are illustrative.

    Returns a complete eif_verify-shaped response so the developer sees exactly
    what a HALT looks like before running their own decision through the pipeline.
    Pre-seeded so developers see the HALT format before their first live verify call.
    """
    halt_card_1 = "\n".join([
        "## 🛑 HALT - Claim Blocked",
        "",
        "**Claim:** `Manor Lords has 3,500+ IGDB hype followers and strong community demand`",
        "",
        "**Why blocked:** EVIDENCE_CONTRADICTS",
        "Evidence from IGDB directly contradicts the stated figure.",
        "",
        "**Evidence:** IGDB API returned 36 hype entries for Manor Lords (id=137206), "
        "not 3,500+. The game released April 2024 (status=4); IGDB hypes reflect "
        "platform-specific anticipation, not Steam wishlists. The 100x gap indicates "
        "the agent conflated Steam wishlist buzz with IGDB-specific metrics.",
        "",
        "**Source:** IGDB public API · P0_HOST_TOOL tier · confidence 0.94",
        "",
        "**Belief claim holds:** 6% | **Residual doubt:** 94%",
        "",
        "**Cost consequence (gaming/content domain):**",
        "  - Expected cost if acted on: **$23,000**",
        "  - Range: $8,000 – $65,000",
        "  - Basis: Content production cost + brand credibility damage "
        "(10-article series based on fabricated demand metrics).",
        "",
        "**Required action:** Verify the IGDB hype count at igdb.com/games/manor-lords "
        "before commissioning the article series. Do not act on this claim.",
    ])

    halt_card_2 = "\n".join([
        "## 🛑 HALT - Claim Blocked",
        "",
        "**Claim:** `Manor Lords has 50,000+ community members in early access`",
        "",
        "**Why blocked:** EVIDENCE_CONTRADICTS",
        "Community size figure cannot be corroborated; contradicted by available data.",
        "",
        "**Evidence:** IGDB does not report a community member count for Manor Lords. "
        "The total_rating_count field shows 32 ratings. Steam community figures are "
        "separate from IGDB metrics and were not cited. No data source supporting "
        "the 50,000+ claim was found in any verifiable API or database.",
        "",
        "**Source:** IGDB public API · P0_HOST_TOOL tier · confidence 0.88",
        "",
        "**Belief claim holds:** 12% | **Residual doubt:** 88%",
        "",
        "**Cost consequence (gaming/content domain):**",
        "  - Expected cost if acted on: **$23,000**",
        "  - Range: $8,000 – $65,000",
        "  - Basis: Same series; dual fabricated metrics compound the credibility risk.",
        "",
        "**Required action:** Locate the actual community source (Steam, Discord, Reddit) "
        "and cite it explicitly before using this figure in any published content brief.",
    ])

    return {
        "is_demo": True,
        "demo_note": (
            "This is a pre-built example using a real gaming-agent failure scenario. "
            "No live API calls were made. Run eif_verify with your own decision to test live claims."
        ),
        "verdict": "HALT",
        "halted_claims": [
            {
                "claim": "Manor Lords has 3,500+ IGDB hype followers and strong community demand",
                "reason": "EVIDENCE_CONTRADICTS",
                "evidence_summary": "IGDB API (id=137206): 36 hypes (not 3,500+). Agent conflated Steam wishlist buzz with IGDB hypes - 100x fabrication.",
                "evidence_source": "IGDB public API · igdb.com/games/manor-lords",
                "posterior": 0.06,
                "cost_impact": {
                    "domain": "gaming",
                    "expected_cost_saved": 23000.0,
                    "dollar_range_low": 8000.0,
                    "dollar_range_high": 65000.0,
                    "citation": "Content production + brand credibility (10-article series based on fabricated demand metrics)",
                },
            },
            {
                "claim": "Manor Lords has 50,000+ community members in early access",
                "reason": "EVIDENCE_CONTRADICTS",
                "evidence_summary": "IGDB does not report a community member count. total_rating_count=32. No verifiable source found for 50,000+ figure.",
                "evidence_source": "IGDB public API · igdb.com/games/manor-lords",
                "posterior": 0.12,
                "cost_impact": {
                    "domain": "gaming",
                    "expected_cost_saved": 23000.0,
                    "dollar_range_low": 8000.0,
                    "dollar_range_high": 65000.0,
                    "citation": "Compound credibility risk from dual fabricated metrics in published content brief",
                },
            },
        ],
        "halt_cards": [halt_card_1, halt_card_2],
        "evidence_trails": [
            {
                "claim": "Manor Lords has 3,500+ IGDB hype followers and strong community demand",
                "verdict": "CONTRADICTS",
                "posterior": 0.06,
                "probe_tier": "P0_HOST_TOOL",
                "evidence_summary": "IGDB API: 36 hypes (not 3,500+). Released April 2024. total_rating=78.4, total_rating_count=32.",
                "evidence_source": "IGDB public API · igdb.com/games/manor-lords",
                "retrieved_at": "2024-04-29T14:23:11Z",
                "self_preference_risk": False,
                "self_preference_overlap": 0.0,
            },
            {
                "claim": "Manor Lords has 50,000+ community members in early access",
                "verdict": "CONTRADICTS",
                "posterior": 0.12,
                "probe_tier": "P0_HOST_TOOL",
                "evidence_summary": "IGDB: no community count field. total_rating_count=32. No verifiable source found for 50,000+ claim.",
                "evidence_source": "IGDB public API · igdb.com/games/manor-lords",
                "retrieved_at": "2024-04-29T14:23:14Z",
                "self_preference_risk": False,
                "self_preference_overlap": 0.0,
            },
        ],
        "retrieval_trace": [
            {"step": 1, "label": "Claims classified", "detail": "0 KNOWN · 0 ASSUMED · 2 GUESSED", "elapsed_ms": 3.1},
            {"step": 2, "label": "Probing claim 1/2", "detail": "Manor Lords has 3,500+ IGDB hype followers…", "elapsed_ms": 3.2},
            {"step": 3, "label": "Evidence result 1/2", "detail": "P0_HOST_TOOL → CONTRADICTS (posterior 0.06)", "elapsed_ms": 48.7},
            {"step": 4, "label": "Probing claim 2/2", "detail": "Manor Lords has 50,000+ community members in early access", "elapsed_ms": 48.8},
            {"step": 5, "label": "Evidence result 2/2", "detail": "P0_HOST_TOOL → CONTRADICTS (posterior 0.12)", "elapsed_ms": 312.4},
            {"step": 6, "label": "Sycophancy gate", "detail": "SKIPPED - no conversation context", "elapsed_ms": 312.5},
            {"step": 7, "label": "Instability probe", "detail": "CLEAN", "elapsed_ms": 312.6},
            {"step": 8, "label": "Verdict", "detail": "HALT - 2 claim(s) halted · total 313 ms", "elapsed_ms": 312.9},
        ],
        "registry_summary": {"known": 0, "assumed": 0, "guessed": 2, "high_risk_assumed": 0, "harking_detected": False},
        "sycophancy_detected": False,
        "self_preference_flagged": [],
        "instability_signals": [],
        "cumulative_cost_protected": {
            "total_expected": 46000.0,
            "halt_count": 2,
            "session_id": "demo",
        },
        "compliance_email_template": None,
        "stale_evidence_warnings": [],
        "next_step": (
            "This is a demo. In your real session: call eif_verify with your own decision "
            "and claims to test whether your agent's outputs are backed by evidence. "
            "The gaming agent above deployed a 10-article series based on fabricated metrics - "
            "EIF would have blocked both claims before content production began."
        ),
    }


@mcp.tool(
    name="eif_get_session",
    description=(
        "Call this after eif_verify to read the full session state: which decisions were recorded, "
        "claim type breakdown per decision, falsification outcomes, and programme status.\n\n"
        "Use this when you need to:\n"
        "- Check how many decisions have been recorded in this session\n"
        "- Inspect per-record claim counts and falsification summary\n"
        "- Check compliance_status before running eif_compliance_report\n\n"
        "Read-only. Does not trigger evidence collection. "
        "Returns: session_id, decisions_recorded, programme_status, compliance_status, "
        "calibration_history_size, records[] (one per ProvenanceRecord; each with record_id, "
        "decision (first 80 chars preview - not the full text), known/assumed/guessed counts, "
        "falsifications_rejected, has_explanation, human_oversight)."
    ),
)
async def eif_get_session(session_id: str) -> dict:
    """Facade: return a clean session overview without triggering any pipeline steps."""
    from eif.programme.monitor import compute_status
    from eif.programme.signals import compute_signals

    sess = await session_store.get_session(session_id)
    chain = sess.provenance_chain

    programme_status = "insufficient_records"
    if len(chain) >= 3:
        signals = compute_signals(chain)
        programme_status = compute_status(signals)

    _log.info("TOOL  eif_get_session  session=%s  records=%d", session_id[:8], len(chain))

    return {
        "session_id": session_id,
        "decisions_recorded": len(chain),
        "programme_status": programme_status,
        "compliance_status": "Article 12 satisfied" if chain else "No records yet",
        "calibration_history_size": len(sess.calibration_history),
        "records": [
            {
                "record_id": r.record_id,
                "decision": r.decision[:80],
                "known": len(r.registry.known),
                "assumed": len(r.registry.assumed),
                "guessed": len(r.registry.guessed),
                "falsifications_rejected": sum(
                    1 for s in r.sprt_results if s.decision == "REJECT"
                ),
                "has_explanation": r.explanation is not None,
                "human_oversight": r.human_oversight,
            }
            for r in chain
        ],
    }


@mcp.tool(
    name="eif_compliance_report",
    description=(
        "Call this after a session with at least one HALT to generate a formatted compliance "
        "report mapping every flagged claim to the relevant EU AI Act article:\n"
        "  Art. 9  - risk management (CAUSAL_UNVERIFIED + HALT)\n"
        "  Art. 12 - record-keeping (provenance trail)\n"
        "  Art. 14 - human oversight (HALT requiring review)\n\n"
        "The report is designed to be forwarded to a compliance officer or auditor without "
        "any additional explanation by the developer. It is a human-readable document - "
        "not a developer log. Always available - no tier restrictions.\n\n"
        "halt_count counts provenance records where ANY calibration posterior < THRESHOLD_HALT (0.20) "
        "OR any SPRT result is REJECT. Per-decision HALTED claim lists use the same posterior signal. "
        "Note: programme_status (PROGRESSIVE/STABLE/DEGENERATIVE) from eif_programme_health and the "
        "programme resource reflects Lakatos research programme health - it is unrelated to the HALT "
        "calculus used here (which is posterior + SPRT-based).\n\n"
        "Parameters: session_id, include_full_evidence (bool, default False - when True, appends "
        "SPRT evidence lines per record inside report_markdown), "
        "export_format ('markdown' default or 'pdf'). "
        "Set export_format='pdf' to write a PDF to ~/.eif/reports/ (requires pip install eif-engine[pdf]). "
        "F17: surfaces DEGRADED_METRIC flags when claims were verified by parametric fallback only "
        "(metric_quality_flags from ProvenanceRecord) - manual review recommended for those claims.\n\n"
        "Returns: report_markdown (formatted text - includes causal_unverified_count aggregate "
        "embedded in the markdown; this count is not a separate structured key), "
        "record_count, halt_count, "
        "articles_covered[], export_ready (True when records exist; False when session is empty - "
        "empty sessions return only export_ready=False and report_markdown with a notice). "
        "When export_format='pdf': pdf_path + pdf_size_bytes on success; pdf_note + pdf_error "
        "when the PDF dependency is missing or the write fails."
    ),
)
async def eif_compliance_report(
    session_id: str,
    include_full_evidence: bool = False,
    export_format: str = "markdown",
) -> dict:
    """Facade: generate a human-readable EU AI Act compliance report.

    export_format: "markdown" (default) or "pdf".
      "pdf" writes a PDF to ~/.eif/reports/ and returns pdf_path + pdf_size_bytes.
      fpdf2 must be installed: pip install eif-engine[pdf]
    """

    sess = await session_store.get_session(session_id)
    chain = sess.provenance_chain

    if not chain:
        return {
            "report_markdown": "No decisions recorded in this session yet. Run eif_verify first.",
            "record_count": 0,
            "halt_count": 0,
            "articles_covered": [],
            "export_ready": False,
        }

    # R6-11: use calibration posterior signals (routing-aligned) instead of the prior
    # guessed/SPRT heuristic. A record is "halted" when ANY calibration posterior falls
    # below THRESHOLD_HALT (the same boundary that determines HALT routing), OR when
    # SPRT explicitly rejected a claim - both indicate a human attention signal.
    halt_count = sum(
        1 for r in chain
        if (
            any(c.posterior < THRESHOLD_HALT for c in r.calibration)
            or any(s.decision == "REJECT" for s in r.sprt_results)
        )
    )
    causal_unverified_count = sum(1 for r in chain if getattr(r, "causal_unverified", False))

    # Aggregate EU AI Act articles from each record's articles_covered map
    # (populated by record/compliance.py::map_compliance during assemble_record).
    # Fall back to inline computation for records assembled before this field
    # existed (in-memory only - persisted records always have it).
    _article_display = {
        "Article 9": "Art. 9 - Risk Management",
        "Article 12": "Art. 12 - Record-keeping and Provenance",
        "Article 13": "Art. 13 - Transparency",
        "Article 14": "Art. 14 - Human Oversight",
    }
    _article_keys: set[str] = set()
    for r in chain:
        covered = getattr(r, "articles_covered", None) or {}
        if covered:
            _article_keys.update(covered.keys())
        else:
            # Backward-compat fallback for records built before articles_covered existed.
            from eif.record.compliance import map_compliance as _map_compliance
            _article_keys.update(_map_compliance(r).keys())
    articles = [_article_display.get(k, k) for k in sorted(_article_keys)]

    lines = [
        "# EIF Compliance Report",
        f"**Session:** `{session_id}`",
        f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Decisions audited:** {len(chain)}",
        f"**Claims flagged (HALT):** {halt_count}",
        f"**Causal claims unverified (CG6/Art.9):** {causal_unverified_count}",
        f"**EU AI Act articles covered:** {', '.join(articles) if articles else 'None'}",
        "",
        "---",
        "",
    ]

    for i, record in enumerate(chain, 1):
        # R7-03: use the same routing signals as halt_count (calibration posterior + SPRT REJECT)
        # so the per-decision narrative matches the summary halt_count.
        _halted_by_post = {c.claim_text for c in record.calibration if c.posterior < THRESHOLD_HALT}
        _halted_by_sprt: set[str] = set()
        for _s in record.sprt_results:
            if _s.decision == "REJECT":
                if _s.claim_text:
                    _halted_by_sprt.add(_s.claim_text)
                else:
                    # Fallback for records assembled before claim_text was added to SPRTResult:
                    # use all falsification condition claim texts as proxy.
                    for _fc in record.falsification_conditions:
                        _halted_by_sprt.add(_fc.claim_text)
        _all_halt_texts = _halted_by_post | _halted_by_sprt
        record_halts = sorted(_all_halt_texts)

        lines.append(f"## Decision {i}: {record.decision[:120]}")
        lines.append(f"**Record ID:** `{record.record_id}`")
        lines.append(f"**Assumptions declared:** {len(record.registry.known) + len(record.registry.assumed) + len(record.registry.guessed)}")
        lines.append(f"**Human oversight:** {record.human_oversight}")

        if record_halts:
            lines.append(f"**HALTED claims ({len(record_halts)}):**")
            for claim in record_halts:
                lines.append(f"  - {claim[:200]}")
            lines.append("**EU AI Act mapping:** Art. 9 (unverified claim in risk context)")

        # CG6: surface CAUSAL_UNVERIFIED flag when HIGH causal claim had no evidence (EU AI Act Art. 9)
        if getattr(record, "causal_unverified", False):
            lines.append(
                "**⚠ CAUSAL_UNVERIFIED:** A HIGH-consequence causal claim in this decision "
                "could not be independently verified. Causal Evidence Probe returned NO_EVIDENCE."
            )
            lines.append("**EU AI Act mapping:** Art. 9 (unverified causal risk - manual review required)")

        if not record_halts and not getattr(record, "causal_unverified", False):
            lines.append("**Verdict:** PASS - no claims halted")

        if include_full_evidence and record.sprt_results:
            lines.append("**Evidence collected:**")
            for sprt in record.sprt_results:
                lines.append(f"  - SPRT {sprt.decision}: {getattr(sprt, 'claim_text', '')[:100]}")

        # F17: surface DEGRADED_METRIC flags for compliance reviewers
        mq_flags = getattr(record, "metric_quality_flags", None) or []
        if mq_flags:
            lines.append(
                f"**Evidence quality flags ({len(mq_flags)}):** "
                "Claims below were verified by parametric fallback only - manual review recommended."
            )
            for flag in mq_flags:
                lines.append(f"  - {flag}")
            lines.append("**EU AI Act mapping:** Art. 9 (degraded evidence quality - verify before acting)")

        lines.append("")

    lines += [
        "---",
        "",
        "## Compliance Statement",
        "",
        "This report documents the epistemic integrity audit conducted by EIF for the above decisions. "
        "Every HALT event represents a claim that could not be verified against external evidence and "
        "was therefore escalated for human review, as required by EU AI Act Article 14. "
        "The provenance chain for this session satisfies Article 12 record-keeping requirements.",
        "",
        f"*Generated by EIF Engine v{ENGINE_VERSION}*",
    ]

    report_md = "\n".join(lines)

    _log.info(
        "TOOL  eif_compliance_report  session=%s  records=%d  halts=%d  articles=%d  format=%s",
        session_id[:8], len(chain), halt_count, len(articles), export_format,
    )

    base_response = {
        "report_markdown": report_md,
        "record_count": len(chain),
        "halt_count": halt_count,
        "articles_covered": articles,
        "export_ready": True,
    }

    if export_format == "pdf":
        try:
            from eif.reporting.pdf_renderer import render_compliance_pdf
            pdf_path = render_compliance_pdf(report_md, session_id)
            base_response["pdf_path"] = str(pdf_path)
            base_response["pdf_size_bytes"] = pdf_path.stat().st_size
            base_response["pdf_note"] = (
                f"PDF written to {pdf_path}. "
                "Open in any PDF viewer or attach to your audit folder."
            )
        except ImportError as exc:
            base_response["pdf_error"] = f"PDF dependency not installed: {exc}"
            base_response["pdf_path"] = None
        except Exception as exc:  # noqa: BLE001
            base_response["pdf_error"] = f"PDF render failed: {exc}"
            base_response["pdf_path"] = None

    return base_response


@mcp.tool(
    name="eif_record_outcome",
    description=(
        "Record the actual outcome of a past decision to close the ECE feedback loop. "
        "Call this after you learn whether a claim the agent made was correct or wrong. "
        "Outcomes are stored cross-session to ~/.eif/outcome_store.json and enable:\n"
        "  1. Label-grounded ECE (F1C1, arXiv:2501.08292) - activates when >= 30 labeled outcome records exist\n"
        "  2. Empirical Bayes prior - replaces max-entropy prior with measured accuracy once >= 10 labeled records\n\n"
        "Parameters:\n"
        "  session_id - EIF session that produced the decision\n"
        "  provenance_record_id - specific ProvenanceRecord.record_id from eif_record output\n"
        "  outcome - True if the agent's claim was correct; False if it was wrong\n"
        "  domain - optional domain tag ('gaming', 'healthcare', etc.) for domain-specific ECE\n\n"
        "Returns: outcome_recorded (bool), outcome_record_id, outcome, domain, "
        "labeled_count (total in store), ece_state, sessions_to_grounded, note."
    ),
)
async def eif_record_outcome(
    session_id: str,
    provenance_record_id: str,
    outcome: bool,
    domain: str | None = None,
) -> dict:
    """Append a labeled outcome to the cross-session outcome store."""
    from eif.record.outcome_store import (
        get_ece_state,
        get_labeled_count,
        get_sessions_to_grounded,
        record_outcome,
    )
    rec = record_outcome(
        session_id=session_id,
        provenance_record_id=provenance_record_id,
        outcome=outcome,
        domain=domain,
    )
    labeled = get_labeled_count()
    ece_state = get_ece_state()
    to_grounded = get_sessions_to_grounded()
    _log.info(
        "TOOL  eif_record_outcome  session=%s record=%s outcome=%s domain=%s labeled=%d",
        session_id, provenance_record_id, outcome, domain, labeled,
    )

    # R5-01 / R6-03: trigger empirical catch-rate recompute whenever a new outcome is recorded.
    # Aggregates ALL in-memory sessions' provenance chains + all outcomes from disk so the
    # stored report reflects the full measurement, not just the triggering session's chain.
    try:
        from eif import session as _session_module  # noqa: PLC0415
        from eif.cost_model.catch_rate_empirical import (  # noqa: PLC0415
            compute_session_catch_rates,
            update_catch_rate_store,
        )
        from eif.record.outcome_store import load_outcomes as _load_outcomes  # noqa: PLC0415
        # Collect provenance chains from ALL loaded sessions (not just the current one)
        # so the catch-rate report reflects cross-session aggregate measurement.
        _all_chains = []
        for _s in _session_module._sessions.values():
            _all_chains.extend(_s.provenance_chain)
        _all_outcomes = _load_outcomes()
        if _all_chains and _all_outcomes:
            _new_report = compute_session_catch_rates(_all_chains, _all_outcomes)
            update_catch_rate_store(_new_report)
            _log.info(
                "TOOL  eif_record_outcome  catch_rate updated: "
                "status=%s sessions_measured=%d f=%.2f c=%s u=%s",
                _new_report.data_status, _new_report.sessions_measured,
                _new_report.f_empirical,
                f"{_new_report.c_empirical:.2f}" if _new_report.c_empirical is not None else "n/a",
                f"{_new_report.u_empirical:.2f}" if _new_report.u_empirical is not None else "n/a",
            )
    except Exception as _cr_exc:  # noqa: BLE001
        _log.warning("eif_record_outcome: catch_rate update failed (non-fatal): %s", _cr_exc)
    return {
        "outcome_recorded": True,
        "outcome_record_id": rec.record_id,
        "outcome": outcome,
        "domain": domain,
        "labeled_count": labeled,
        "ece_state": ece_state,
        "sessions_to_grounded": to_grounded,
        "note": (
            f"ECE remains LABEL_GROUNDED - real outcomes active (labeled_count={labeled})."
            if ece_state == "LABEL_GROUNDED" and labeled > 30
            else "ECE is now LABEL_GROUNDED - using real outcomes for calibration."
            if ece_state == "LABEL_GROUNDED"
            else f"{to_grounded} more labeled outcome record(s) needed before ECE activates "
                 "(currently using tier-proxy approximation)."
        ),
    }


@mcp.tool(
    name="eif_calibration_report",
    description=(
        "Return the current state of the ECE calibration feedback loop across all sessions. "
        "Use this to understand:\n"
        "  - How many outcome records have been labeled (count is OutcomeRecord rows, not unique sessions)\n"
        "  - Whether ECE is LABEL_GROUNDED (>= 30 labeled records globally) or UNCALIBRATED (< 30)\n"
        "  - What the empirical prior is for a domain (mean accuracy across labeled outcome records)\n"
        "  - How many more labeled outcome records are needed before ECE activates\n\n"
        "ECE grounding semantics (R10-01):\n"
        "  - GLOBAL (this tool): ece_state is LABEL_GROUNDED when >= 30 OutcomeRecord rows exist in the "
        "store across all sessions.\n"
        "  - PER-SESSION (eif_calibrate): ece_label_grounded is True only when >= 30 labeled "
        "(posterior, outcome) pairs are aligned for THAT session. These two can differ - "
        "global can be LABEL_GROUNDED while a specific session is still False.\n\n"
        "Call eif_record_outcome to add labeled outcome records. "
        "Optional: pass domain to filter by topic area.\n\n"
        "Returns: domain (resolved key, 'all' when no domain passed), "
        "labeled_count, ece_state, empirical_prior, empirical_prior_note, sessions_to_grounded."
    ),
)
async def eif_calibration_report(domain: str | None = None) -> dict:
    """Return current ECE state and empirical prior for the outcome store."""
    from eif.record.outcome_store import (
        compute_empirical_prior,
        get_ece_state,
        get_labeled_count,
        get_sessions_to_grounded,
    )
    labeled = get_labeled_count(domain)
    ece_state = get_ece_state(domain)
    to_grounded = get_sessions_to_grounded(domain)
    prior = compute_empirical_prior(domain)
    _log.info("TOOL  eif_calibration_report  domain=%s labeled=%d ece=%s", domain, labeled, ece_state)
    return {
        "domain": domain or "all",
        "labeled_count": labeled,
        "ece_state": ece_state,
        "sessions_to_grounded": to_grounded,
        "empirical_prior": prior,
        "empirical_prior_note": (
            f"empirical_prior is the measured accuracy rate across labeled outcome records "
            f"for domain={domain or 'all'} (from outcome_store, via eif_record_outcome). "
            "This is a derived statistic - it reports what the outcome store currently contains. "
            "It is NOT automatically applied as the dynamic Bayes prior inside eif_calibrate; "
            "eif_calibrate uses its own session calibration_history for the empirical prior "
            "(gates on PRIOR_EMPIRICAL_MIN=10 per-session entries). "
            "To use empirical_prior as the prior in eif_calibrate, pass it explicitly as the `prior` argument."
        ),
    }


@mcp.tool(
    name="eif_catch_rate_report",
    description=(
        "Return empirical catch rates for the compound error model, measured from "
        "labeled EIF sessions.\n\n"
        "The compound error model uses f (FALSIFY), c (CHALLENGE), u (UPDATE) rates "
        "to estimate the fraction of errors that survive all three phases. "
        "Literature defaults: f=0.6, c=0.4, u=0.5 (Architecture §9.2). "
        "These have not been measured on actual EIF data - this report bridges that gap.\n\n"
        "data_status (based on outcome-linked provenance records, not unique session count):\n"
        "  INSUFFICIENT_DATA - < 3 records measured; literature defaults used\n"
        "  PARTIAL           - 3–4 records; empirical rates shown but not yet primary\n"
        "  SUFFICIENT        - >= 5 records; empirical rates replace literature defaults\n\n"
        "Returns a nested structure - NOT flat fields:\n"
        "  data_status, sessions_measured,\n"
        "  empirical.{f, c, u, compound_error},\n"
        "  literature.{f, c, u, compound_error},\n"
        "  used_for_calculation.{f, c, u},\n"
        "  note."
    ),
)
async def eif_catch_rate_report() -> dict:
    """Return current empirical catch rate estimates vs. literature defaults."""
    from eif.cost_model.catch_rate_empirical import get_catch_rate_report
    report = get_catch_rate_report()
    _log.info(
        "TOOL  eif_catch_rate_report  status=%s sessions=%d",
        report.data_status, report.sessions_measured,
    )
    return {
        "data_status": report.data_status,
        "sessions_measured": report.sessions_measured,
        "empirical": {
            "f": report.f_empirical,
            "c": report.c_empirical,
            "u": report.u_empirical,
            "compound_error": report.compound_error_empirical,
        },
        "literature": {
            "f": report.f_literature,
            "c": report.c_literature,
            "u": report.u_literature,
            "compound_error": report.compound_error_literature,
        },
        "used_for_calculation": {
            "f": report.f_used,
            "c": report.c_used,
            "u": report.u_used,
        },
        "note": (
            "Empirical rates replace literature defaults once >= 5 outcome-linked provenance "
            f"records are measured. Current status: {report.data_status}."
        ),
    }


def main() -> None:
    """Console script entrypoint for `eif-mcp-server`."""
    import sys

    if "--version" in sys.argv:
        print(f"eif-engine {ENGINE_VERSION}")
        return
    if "--help" in sys.argv or "-h" in sys.argv:
        print(
            "eif-mcp-server - EIF MCP server (stdio transport)\n\n"
            "Runs the 25-tool EIF pipeline over stdio for MCP clients\n"
            "(Cursor, Claude Desktop, Claude Code). No arguments needed;\n"
            "point your MCP client at this command.\n\n"
            "Options:\n"
            "  --version   print version and exit\n"
            "  -h, --help  show this help and exit"
        )
        return

    _log.info("=" * 60)
    _log.info("EIF MCP server started  (stdio transport)  v%s", ENGINE_VERSION)
    _log.info("Log: %s", _LOG_PATH)
    _log.info("=" * 60)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

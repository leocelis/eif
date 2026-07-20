"""Empirical catch rate measurement for the compound error model (F14).

The compound error model (Architecture §9.2) uses literature-derived rates:
  f = 0.6 (FALSIFY catch rate)   - analogous to POPPER mechanism
  u = 0.5 (UPDATE routing delta) - analogous to LAPD mechanism
  c = 0.4 (CHALLENGE hit rate)   - multi-agent literature estimates

The cross-check audit §5.1 flags explicitly: "These have not been measured on
an actual EIF implementation." This module closes that gap by computing actual
rates from outcome-linked provenance records (OutcomeRecord rows in the outcome_store).

Definitions:
  f_empirical - FALSIFY catch rate:
    fraction of HIGH-consequence WRONG claims (outcome=False) that were
    caught by FALSIFY (SPRT REJECT or trivial_flag=True).
    A claim is "caught" when the engine raised a flag that a decision-maker
    would notice. Denominator: total HIGH-consequence claims in labeled-wrong sessions.

  c_empirical - CHALLENGE hit rate:
    fraction of ProvenanceRecords where ChallengeResult.counter_evidence_found=True.
    Denominator: all records that ran the CHALLENGE phase (challenge is not None).

  u_empirical - UPDATE routing-change rate:
    fraction of ProvenanceRecords where UPDATE changed routing across a threshold
    boundary (ACT↔REVISE or REVISE↔HALT). Uses UpdateResult pairs inside a record.
    Denominator: records that have >= 1 UpdateResult.

The store (~/.eif/catch_rates.json) accumulates statistics across sessions using
a running mean. When >= 5 outcome-linked provenance records are measured (F14C3),
empirical rates replace literature defaults in the compound error calculation.

Research:
  EIF Architecture §9.2 - compound error model with f, u, c parameters.
  Cross-check audit §5.1 - "not measured on actual EIF data; may be off 20-30%".
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from eif.schemas import (
    THRESHOLD_ACT,
    THRESHOLD_HALT,
    CatchRateReport,
    OutcomeRecord,
    ProvenanceRecord,
)

_log = logging.getLogger("eif.catch_rate_empirical")

# Literature defaults from Architecture §9.2 and v3 intent F14 problem text:
#   f = 0.6 (FALSIFY catch rate)       - POPPER-analogous mechanism
#   c = 0.4 (CHALLENGE hit rate)       - multi-agent literature estimates
#   u = 0.5 (UPDATE routing-change)    - LAPD-analogous mechanism
# NOTE: earlier code had c=0.5/u=0.4 (swapped vs intent). Fixed to match intent.
_F_LIT: float = 0.6
_C_LIT: float = 0.4   # CHALLENGE - was incorrectly 0.5
_U_LIT: float = 0.5   # UPDATE   - was incorrectly 0.4

# How many sessions needed before empirical rates replace literature defaults
EMPIRICAL_MIN_SESSIONS: int = 5
PARTIAL_MIN_SESSIONS: int = 3


def _store_path() -> Path:
    base = os.environ.get("EIF_STORE_DIR", os.path.expanduser("~/.eif"))
    path = Path(base) / "catch_rates.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Measurement functions
# ─────────────────────────────────────────────────────────────────────────────


def compute_session_catch_rates(
    provenance_chain: list[ProvenanceRecord],
    outcome_records: list[OutcomeRecord],
) -> CatchRateReport:
    """Compute per-phase catch rates from a session's provenance chain and labeled outcomes.

    outcome_records: labeled outcomes from the outcome_store for this session.
    When outcome_records is empty, f_empirical is None (no ground truth).

    Returns a CatchRateReport with empirical measurements and compound error
    residuals using BOTH empirical and literature rates.
    """
    # Build lookup: provenance_record_id → outcome (True/False)
    outcome_map: dict[str, bool] = {
        o.provenance_record_id: o.outcome for o in outcome_records
    }

    # ── f_empirical: FALSIFY catch rate ──────────────────────────────────────
    # f_empirical = 0.0 when denominator is 0 (no labeled wrong claims - intent F14C1).
    # This is distinct from None: 0.0 means "measured, nothing to catch";
    # data_status INSUFFICIENT_DATA prevents it from replacing the literature default.
    f_empirical: float = 0.0
    wrong_claims_total = 0
    wrong_claims_caught = 0

    for record in provenance_chain:
        rec_outcome = outcome_map.get(record.record_id)
        if rec_outcome is None:
            continue  # unlabeled - skip for catch-rate denominator
        if rec_outcome is True:
            continue  # agent was correct - not a "wrong" session to catch

        # Session was wrong (outcome=False)
        # F14C1: denominator = HIGH-consequence claims only (intent is explicit).
        # CalibrationResult now carries consequence_of_wrong; for records assembled
        # before that field was added, fall back to all ASSUMED+GUESSED as proxy.
        high_claims = [
            c for c in record.calibration if c.consequence_of_wrong == "HIGH"
        ] if record.calibration else []
        if not high_claims:
            # Fallback: use ASSUMED+GUESSED from registry (pre-field migration records)
            n_at_risk = len(record.registry.guessed) + len(record.registry.assumed)
        else:
            n_at_risk = len(high_claims)

        # Caught: any SPRT REJECT or trivial_flag=True in falsification conditions
        has_reject = any(s.decision == "REJECT" for s in record.sprt_results)
        has_trivial = any(fc.trivial_flag for fc in record.falsification_conditions)
        caught = has_reject or has_trivial

        wrong_claims_total += max(1, n_at_risk)
        if caught:
            wrong_claims_caught += max(1, n_at_risk)

    if wrong_claims_total > 0:
        f_empirical = wrong_claims_caught / wrong_claims_total

    # ── c_empirical: CHALLENGE counter-evidence hit rate ─────────────────────
    c_empirical: float | None = None
    challenged_records = [r for r in provenance_chain if r.challenge is not None]
    if challenged_records:
        c_empirical = sum(
            1 for r in challenged_records if r.challenge.counter_evidence_found
        ) / len(challenged_records)

    # ── u_empirical: UPDATE routing-change rate ───────────────────────────────
    u_empirical: float | None = None
    records_with_updates = [r for r in provenance_chain if r.updates]
    if records_with_updates:
        routing_changes = 0
        for record in records_with_updates:
            if len(record.updates) < 1:
                continue
            first_update = record.updates[0]
            last_update = record.updates[-1]
            routing_changed = _routing_bucket(first_update.prior_posterior) != \
                              _routing_bucket(last_update.updated_posterior)
            if routing_changed:
                routing_changes += 1
        u_empirical = routing_changes / len(records_with_updates)

    # ── Determine data status ─────────────────────────────────────────────────
    labeled_count = len([r for r in provenance_chain if r.record_id in outcome_map])
    if labeled_count >= EMPIRICAL_MIN_SESSIONS:
        data_status = "SUFFICIENT"
    elif labeled_count >= PARTIAL_MIN_SESSIONS:
        data_status = "PARTIAL"
    else:
        data_status = "INSUFFICIENT_DATA"

    # ── Determine which rates to use for primary calculation ──────────────────
    use_empirical = data_status == "SUFFICIENT"
    f_used = f_empirical if (use_empirical and f_empirical is not None) else _F_LIT
    c_used = c_empirical if (use_empirical and c_empirical is not None) else _C_LIT
    u_used = u_empirical if (use_empirical and u_empirical is not None) else _U_LIT

    # ── Compound error residuals ───────────────────────────────────────────────
    # R6-06: when data_status reaches SUFFICIENT but c/u phases never ran (no
    # CHALLENGE or UPDATE calls in this corpus), fill missing legs with literature
    # defaults so compound_error_empirical is always populated once f is measured.
    # The note field already flags INSUFFICIENT data for unavailable rates.
    compound_empirical: float | None = None
    if f_empirical is not None:
        _c_for_compound = c_empirical if c_empirical is not None else _C_LIT
        _u_for_compound = u_empirical if u_empirical is not None else _U_LIT
        compound_empirical = (1 - f_empirical) * (1 - _c_for_compound) * (1 - _u_for_compound)

    compound_literature = (1 - _F_LIT) * (1 - _C_LIT) * (1 - _U_LIT)

    return CatchRateReport(
        f_empirical=f_empirical,
        c_empirical=c_empirical,
        u_empirical=u_empirical,
        sessions_measured=labeled_count,  # count of outcome-linked provenance records (not unique session_ids)
        data_status=data_status,
        f_literature=_F_LIT,
        c_literature=_C_LIT,
        u_literature=_U_LIT,
        compound_error_empirical=compound_empirical,
        compound_error_literature=compound_literature,
        f_used=f_used,
        c_used=c_used,
        u_used=u_used,
        generated_at=datetime.utcnow(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Persistent store
# ─────────────────────────────────────────────────────────────────────────────


def load_catch_rate_store() -> CatchRateReport | None:
    """Load the latest CatchRateReport from disk, or None if not present."""
    path = _store_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return CatchRateReport.model_validate(raw)
    except Exception as exc:
        _log.warning("catch_rate_store: could not load %s (%s)", path, exc)
        return None


def update_catch_rate_store(report: CatchRateReport) -> None:
    """Persist a CatchRateReport to disk atomically."""
    path = _store_path()
    data = report.model_dump(mode="json")
    _atomic_write(path, data)
    _log.info(
        "catch_rate_store: updated (outcome_linked_records=%d, status=%s, f=%.2f c=%.2f u=%.2f)",
        report.sessions_measured, report.data_status,
        report.f_used, report.c_used, report.u_used,
    )


def get_catch_rate_report() -> CatchRateReport:
    """Return the stored CatchRateReport, or a fresh default with literature values."""
    stored = load_catch_rate_store()
    if stored is not None:
        return stored
    return CatchRateReport(
        data_status="INSUFFICIENT_DATA",
        compound_error_literature=(1 - _F_LIT) * (1 - _C_LIT) * (1 - _U_LIT),
        generated_at=datetime.utcnow(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _routing_bucket(posterior: float) -> str:
    if posterior >= THRESHOLD_ACT:
        return "ACT"
    elif posterior >= THRESHOLD_HALT:
        return "REVISE"
    return "HALT"


def _atomic_write(path: Path, data: dict) -> None:
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

"""Cross-session outcome persistence - Session Outcome Feedback Loop (F11).

Closes the feedback gap that kept label-grounded ECE (F1C1) permanently
UNCALIBRATED: sessions are in-memory and evaporate at process restart, so
outcome_observed on ProvenanceRecord was never persisted across sessions.

Store location: ~/.eif/outcome_store.json  (configurable via EIF_STORE_DIR env var)
Format: JSON array of OutcomeRecord dicts, append-only.

The store provides two inputs to the calibration pipeline:
  1. Label-grounded ECE (F1C1, arXiv:2501.08292): activates when >= 30 labeled
     records exist. Requires (predicted_confidence, actual_outcome) pairs.
  2. Empirical Bayes prior (Architecture §5.4 Strategy 2): compute_empirical_prior()
     returns mean accuracy rate across labeled outcome records for a domain. Falls back
     to 0.5 (max_entropy) when < PRIOR_EMPIRICAL_MIN (10) records for that domain.

Thread safety: file writes use atomic replace (write tmp → os.replace). No
in-process lock is needed for append-only single-writer use from the MCP server.
For concurrent writers (multi-process deployments), add an advisory file lock.

Research:
  arXiv:2501.08292 - label-grounded ECE; requires binary outcome labels.
  EIF Architecture §5.4 - three prior strategies; Strategy 2 needs outcome history.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from eif.schemas import PRIOR_EMPIRICAL_MIN, OutcomeRecord

_log = logging.getLogger("eif.outcome_store")

# Minimum labeled outcome records (OutcomeRecord rows) for label-grounded ECE to activate (F1C1).
# Must align with ece.py ECE_LABEL_MIN = 30.
ECE_GROUNDED_MIN: int = 30


def _store_path() -> Path:
    """Resolve the outcome store path.

    Uses EIF_STORE_DIR env var when set; otherwise ~/.eif/outcome_store.json.
    Creates the parent directory if it does not exist.
    """
    base = os.environ.get("EIF_STORE_DIR", os.path.expanduser("~/.eif"))
    path = Path(base) / "outcome_store.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Core store operations
# ─────────────────────────────────────────────────────────────────────────────


def load_outcomes() -> list[OutcomeRecord]:
    """Load all OutcomeRecords from the store.

    Returns an empty list when the file does not exist. Logs a warning and
    returns an empty list on corruption (does not delete the file).
    """
    path = _store_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            _log.warning("outcome_store: expected list, got %s - returning empty", type(raw).__name__)
            return []
        return [OutcomeRecord.model_validate(r) for r in raw]
    except Exception as exc:
        _log.warning("outcome_store: could not load %s (%s) - returning empty", path, exc)
        return []


def record_outcome(
    session_id: str,
    provenance_record_id: str,
    outcome: bool,
    domain: str | None = None,
) -> OutcomeRecord:
    """Append a labeled outcome to the store and return the new OutcomeRecord.

    Append-only: existing entries are never modified. Uses atomic write
    (tempfile → os.replace) to prevent corrupt partial writes.
    """
    record = OutcomeRecord(
        session_id=session_id,
        provenance_record_id=provenance_record_id,
        outcome=outcome,
        domain=domain,
        recorded_at=datetime.utcnow(),
    )
    path = _store_path()
    existing = load_outcomes()
    updated = existing + [record]
    _atomic_write(path, [r.model_dump(mode="json") for r in updated])
    _log.info(
        "outcome_store: recorded outcome=%s session=%s domain=%s (total=%d)",
        outcome, session_id, domain, len(updated),
    )
    return record


def clear_store_for_testing(store_dir: str) -> None:
    """Delete the outcome store file in a given directory (test-only helper).

    Never touches ~/.eif/ directly. Only operates on paths under store_dir.
    """
    path = Path(store_dir) / "outcome_store.json"
    if path.exists():
        path.unlink()


# ─────────────────────────────────────────────────────────────────────────────
# Calibration helpers
# ─────────────────────────────────────────────────────────────────────────────


def compute_empirical_prior(domain: str | None = None) -> float:
    """Return mean accuracy rate (outcome=True fraction) for a domain.

    Returns 0.5 (max_entropy) when fewer than PRIOR_EMPIRICAL_MIN (10) labeled
    records exist for the requested domain (or overall when domain=None).

    Used as the Bayesian prior in Architecture §5.4 Strategy 2.
    """
    outcomes = load_outcomes()
    if domain is not None:
        outcomes = [o for o in outcomes if o.domain == domain]
    if len(outcomes) < PRIOR_EMPIRICAL_MIN:
        return 0.5
    return sum(1 for o in outcomes if o.outcome) / len(outcomes)


def get_labeled_count(domain: str | None = None) -> int:
    """Return total number of labeled records in the store (optionally filtered by domain)."""
    outcomes = load_outcomes()
    if domain is not None:
        outcomes = [o for o in outcomes if o.domain == domain]
    return len(outcomes)


def get_ece_state(domain: str | None = None) -> str:
    """Return 'LABEL_GROUNDED' when >= 30 labeled outcome records exist, else 'UNCALIBRATED'."""
    n = get_labeled_count(domain)
    return "LABEL_GROUNDED" if n >= ECE_GROUNDED_MIN else "UNCALIBRATED"


def get_sessions_to_grounded(domain: str | None = None) -> int:
    """Return how many more labeled outcome records (OutcomeRecord rows) are needed before ECE activates."""
    return max(0, ECE_GROUNDED_MIN - get_labeled_count(domain))


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _atomic_write(path: Path, data: list[dict]) -> None:
    """Write JSON to path atomically using a temp file in the same directory."""
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

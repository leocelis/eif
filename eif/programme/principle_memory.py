"""Persistent principle space memory for PIEVO (F3).

PIEVO (arXiv:2602.06448) requires an evolving principle space - not just
single-shot proposals, but a memory that accumulates accepted revisions
across sessions so future proposals build on what prior anomalies revealed.

Storage: ~/.eif/principle_memory.json
Override: EIF_PRINCIPLE_MEMORY_PATH environment variable.

Schema (per domain):
  {
    "revision_history": [
      {
        "session_id": str,
        "direction": "DOWN" | "UP" | "MIXED",
        "affected_principle": str,
        "revision_direction": str,
        "confidence": float,
        "alternative_hypotheses": [str],
        "accepted": bool,
        "recorded_at": ISO8601 str
      }
    ],
    "current_principle_state": str,  # latest accepted principle for this domain
    "total_anomalies": int,
    "accepted_revisions": int,
    "rejected_revisions": int
  }

Usage:
    from eif.programme.principle_memory import load_principle_memory, record_revision
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

_log = logging.getLogger(__name__)

_DEFAULT_PATH = Path.home() / ".eif" / "principle_memory.json"


def _get_memory_path() -> Path:
    env = os.environ.get("EIF_PRINCIPLE_MEMORY_PATH")
    return Path(env) if env else _DEFAULT_PATH


def load_principle_memory(domain: str | None = None) -> dict:
    """Load principle memory from disk.

    Args:
        domain: If provided, return only this domain's history.
                If None, return the full memory dict.

    Returns:
        dict of {domain: {revision_history, current_principle_state, ...}}
        or a single domain dict if domain is specified.
    """
    path = _get_memory_path()
    if not path.exists():
        return {} if domain is None else _empty_domain()

    try:
        with path.open("r", encoding="utf-8") as f:
            memory = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        _log.warning("principle_memory: could not read %s (%s) - starting fresh", path, exc)
        return {} if domain is None else _empty_domain()

    if domain is not None:
        return memory.get(domain, _empty_domain())

    return memory


def record_revision(
    domain: str,
    session_id: str,
    direction: str,
    affected_principle: str,
    revision_direction: str,
    confidence: float,
    alternative_hypotheses: list[str],
    accepted: bool,
) -> None:
    """Persist a principle revision attempt (accepted or rejected) to disk.

    Args:
        domain:                 Domain key (e.g. "gaming_content", "investment").
        session_id:             EIF session that triggered this revision.
        direction:              ParadigmRevisionAlert direction (DOWN/UP/MIXED).
        affected_principle:     The principle identified as driving the drift.
        revision_direction:     The proposed change to that principle.
        confidence:             Confidence of the proposal (≤ 0.80).
        alternative_hypotheses: Non-revision explanations for the anomaly.
        accepted:               True if the user confirmed the revision.
    """
    path = _get_memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    memory = load_principle_memory()

    domain_data = memory.get(domain, _empty_domain())

    entry = {
        "session_id": session_id,
        "direction": direction,
        "affected_principle": affected_principle,
        "revision_direction": revision_direction,
        "confidence": confidence,
        "alternative_hypotheses": alternative_hypotheses,
        "accepted": accepted,
        "recorded_at": datetime.now(UTC).isoformat(),
    }

    domain_data["revision_history"].append(entry)
    domain_data["total_anomalies"] += 1

    if accepted:
        domain_data["accepted_revisions"] += 1
        domain_data["current_principle_state"] = revision_direction
    else:
        domain_data["rejected_revisions"] += 1

    memory[domain] = domain_data

    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2)
    except OSError as exc:
        _log.warning("principle_memory: could not write to %s (%s)", path, exc)


def get_principle_context(domain: str) -> dict:
    """Return the current principle state and recent revision history for a domain.

    Used by propose_principle_revision() to inform new proposals with accumulated
    knowledge - implementing PIEVO's evolving principle space.

    Returns:
        {
          "current_state": str | None,       # last accepted principle revision
          "recent_anomalies": list[dict],    # last 5 anomalies (accepted or not)
          "accepted_count": int,
          "rejected_count": int,
          "prior_alternatives": list[str],   # alternatives from all past proposals
        }
    """
    domain_data = load_principle_memory(domain)
    history = domain_data.get("revision_history", [])

    recent = history[-5:] if len(history) > 5 else history
    prior_alternatives: list[str] = []
    for entry in history:
        prior_alternatives.extend(entry.get("alternative_hypotheses", []))

    return {
        "current_state": domain_data.get("current_principle_state"),
        "recent_anomalies": recent,
        "accepted_count": domain_data.get("accepted_revisions", 0),
        "rejected_count": domain_data.get("rejected_revisions", 0),
        "prior_alternatives": list(dict.fromkeys(prior_alternatives))[:10],
    }


def _empty_domain() -> dict:
    return {
        "revision_history": [],
        "current_principle_state": None,
        "total_anomalies": 0,
        "accepted_revisions": 0,
        "rejected_revisions": 0,
    }

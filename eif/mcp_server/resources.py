"""EIF MCP resource handler implementations."""

from __future__ import annotations

import json
import logging

from eif import session as session_store
from eif.programme.monitor import compute_status
from eif.programme.signals import compute_signals

_log = logging.getLogger(__name__)


async def get_summary(session_id: str) -> str:
    """Return a compact session summary as JSON."""
    try:
        sess = await session_store.get_session(session_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    chain = sess.provenance_chain
    n_records = len(chain)

    known_count = sum(len(r.registry.known) for r in chain)
    assumed_count = sum(len(r.registry.assumed) for r in chain)
    guessed_count = sum(len(r.registry.guessed) for r in chain)
    falsifications_run = sum(len(r.sprt_results) for r in chain)
    falsifications_rejected = sum(
        sum(1 for s in r.sprt_results if s.decision == "REJECT")
        for r in chain
    )
    explanations_produced = sum(1 for r in chain if r.explanation is not None)

    signals = compute_signals(chain)
    status = compute_status(signals)

    _log.info("RESOURCE  summary  session=%s  records=%d", session_id[:8], n_records)

    return json.dumps({
        "session_id": session_id,
        "decisions_recorded": n_records,
        "assumptions_declared": known_count + assumed_count + guessed_count,
        "known_count": known_count,
        "assumed_count": assumed_count,
        "guessed_count": guessed_count,
        "falsifications_run": falsifications_run,
        "falsifications_rejected": falsifications_rejected,
        "explanations_produced": explanations_produced,
        "programme_status": status,
        "compliance_status": "Article 12 satisfied" if n_records > 0 else "No records yet",
    }, indent=2)


async def get_registry(session_id: str) -> str:
    """Return the latest AssumptionRegistry as JSON.

    R6-05: falls back to last_registry (persisted by eif_declare / eif_verify) when
    the provenance chain is empty - granular pipelines call eif_declare before the
    first eif_record, so the chain may be empty while a real registry already exists.
    """
    try:
        sess = await session_store.get_session(session_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    if sess.provenance_chain:
        return json.dumps(sess.provenance_chain[-1].registry.model_dump(), indent=2, default=str)

    if sess.last_registry:
        return json.dumps(sess.last_registry, indent=2, default=str)

    return json.dumps({"error": "No registry found - call eif_declare or eif_verify first"})


async def get_provenance(session_id: str) -> str:
    """Return full provenance chain as JSON."""
    try:
        sess = await session_store.get_session(session_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    chain_data = [r.model_dump() for r in sess.provenance_chain]
    return json.dumps(chain_data, indent=2, default=str)


async def get_programme(session_id: str) -> str:
    """Return ProgrammeSignals as JSON.

    Always recomputes fresh from the provenance chain so the resource reflects
    the most current chain state. SessionState.programme (written by
    eif_programme_health) is a snapshot and is intentionally not used here.
    """
    try:
        sess = await session_store.get_session(session_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    signals = compute_signals(sess.provenance_chain)
    status = compute_status(signals)
    updated = signals.model_copy(update={"status": status})
    return json.dumps(updated.model_dump(), indent=2)


async def get_calibration(session_id: str) -> str:
    """Return calibration history as JSON."""
    try:
        sess = await session_store.get_session(session_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    cal_data = [c.model_dump() for c in sess.calibration_history]
    return json.dumps(cal_data, indent=2, default=str)

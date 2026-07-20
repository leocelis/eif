"""Append ProvenanceRecord to the session's provenance chain."""

from __future__ import annotations

import logging

from eif.schemas import ProvenanceRecord, SessionState

_log = logging.getLogger(__name__)


def append_to_chain(
    session: SessionState,
    record: ProvenanceRecord,
) -> SessionState:
    """Append record to the session's provenance_chain, ensuring unique record_id.

    Returns an updated SessionState (immutable update via model_copy).
    """
    existing_ids = {r.record_id for r in session.provenance_chain}
    if record.record_id in existing_ids:
        _log.warning("Duplicate record_id %s - skipping append", record.record_id)
        return session

    new_chain = session.provenance_chain + [record]
    updated = session.model_copy(update={"provenance_chain": new_chain})
    _log.info(
        "RECORD  chain_append  session=%s  record=%s  chain_length=%d",
        session.session_id[:8],
        record.record_id[:8],
        len(new_chain),
    )
    return updated

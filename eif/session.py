"""EIF session state - async in-memory store with per-session locks.

Every session has an owner: the tenant of the request that created it, or
None (operator key, development, stdio). A session is visible only to a
caller with the same owner; any other caller gets the same "not found or
expired" error as a session that does not exist, so the answer does not
reveal that the id is real.

The caller's tenant comes from `caller_tenant`, a context variable the MCP
dispatch and POST /verify set for the duration of each message. Every
function here also takes it explicitly as `tenant=`.
"""

from __future__ import annotations

import asyncio
import contextvars
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta

from eif.schemas import SessionState

_sessions: dict[str, SessionState] = {}
_owners: dict[str, str] = {}  # session_id -> tenant; absent = no owner
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

SESSION_TTL = timedelta(hours=24)

# The tenant of the message being handled; None = no tenant.
caller_tenant: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "eif_caller_tenant", default=None
)

_CALLER = object()  # default for tenant=: read caller_tenant


@contextmanager
def caller_scope(tenant: str | None):
    """Run a block as `tenant` (None = no tenant)."""
    token = caller_tenant.set(tenant)
    try:
        yield
    finally:
        caller_tenant.reset(token)


def _resolve(tenant) -> str | None:
    return caller_tenant.get() if tenant is _CALLER else tenant


def _not_found(session_id: str) -> ValueError:
    return ValueError(
        f"Session {session_id!r} not found or expired. "
        "Call eif_new_session first and pass its session_id to this tool."
    )


def owner_of(session_id: str) -> str | None:
    return _owners.get(session_id)


def visible_to(session_id: str, tenant=_CALLER) -> bool:
    """True if the session exists for this caller (same owner)."""
    return session_id in _sessions and _owners.get(session_id) == _resolve(tenant)


async def new_session(linked_session_id: str | None = None, tenant=_CALLER) -> SessionState:
    owner = _resolve(tenant)
    session = SessionState(linked_session_id=linked_session_id)
    async with _locks[session.session_id]:
        _sessions[session.session_id] = session
        if owner:
            _owners[session.session_id] = owner
    return session


async def get_session(session_id: str, tenant=_CALLER) -> SessionState:
    session = _sessions.get(session_id)
    if session is None or _owners.get(session_id) != _resolve(tenant):
        raise _not_found(session_id)
    age = datetime.utcnow() - session.created_at
    if age > SESSION_TTL:
        del _sessions[session_id]
        _owners.pop(session_id, None)
        raise ValueError(
            f"Session {session_id!r} expired after {SESSION_TTL}. "
            "Call eif_new_session to start a new one."
        )
    return session


async def update_session(session_id: str, tenant=_CALLER, **kwargs) -> SessionState:
    async with _locks[session_id]:
        session = await get_session(session_id, tenant=tenant)
        updated = session.model_copy(update=kwargs)
        _sessions[session_id] = updated
        return updated


async def note_complyedge_event(session_id: str, entry: dict, tenant=_CALLER) -> None:
    """Append one ComplyEdge Log ID to a live session; no-op if there is none.

    A Log ID is metadata about a call, so a missing or expired session never
    fails the call it belongs to. A session the caller does not own counts as
    missing.
    """
    async with _locks[session_id]:
        session = _sessions.get(session_id)
        if session is None or datetime.utcnow() - session.created_at > SESSION_TTL:
            return
        if _owners.get(session_id) != _resolve(tenant):
            return
        _sessions[session_id] = session.model_copy(
            update={"complyedge_event_ids": [*session.complyedge_event_ids, entry]}
        )

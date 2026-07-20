"""EIF session state - async in-memory store with per-session locks."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

from eif.schemas import SessionState

_sessions: dict[str, SessionState] = {}
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

SESSION_TTL = timedelta(hours=24)


async def new_session(linked_session_id: str | None = None) -> SessionState:
    session = SessionState(linked_session_id=linked_session_id)
    async with _locks[session.session_id]:
        _sessions[session.session_id] = session
    return session


async def get_session(session_id: str) -> SessionState:
    session = _sessions.get(session_id)
    if session is None:
        raise ValueError(
            f"Session {session_id!r} not found or expired. "
            "Call eif_new_session first and pass its session_id to this tool."
        )
    age = datetime.utcnow() - session.created_at
    if age > SESSION_TTL:
        del _sessions[session_id]
        raise ValueError(
            f"Session {session_id!r} expired after {SESSION_TTL}. "
            "Call eif_new_session to start a new one."
        )
    return session


async def update_session(session_id: str, **kwargs) -> SessionState:
    async with _locks[session_id]:
        session = await get_session(session_id)
        updated = session.model_copy(update=kwargs)
        _sessions[session_id] = updated
        return updated

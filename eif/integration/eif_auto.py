"""eif_auto - generic EIF guard for any Python agent.

Works without LangChain. Wraps any async function that produces a decision
string, extracts claims from its output, and runs eif_verify inline.

Usage - decorator:

    from eif.integration.eif_auto import eif_guard

    @eif_guard(session_id="my-session")
    async def decide(task: str) -> str:
        return await llm.complete(task)

    # EIFHaltError is raised if any claim is HALT-routed.
    # The error carries the full eif_verify response.

Usage - context manager:

    from eif.integration.eif_auto import EIFSession, EIFHaltError

    async with EIFSession(session_id="s1") as guard:
        decision = await agent.run(task)
        result = await guard.verify(decision)   # raises EIFHaltError on HALT
        # result is the full eif_verify response dict
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# EIFHaltError - raised when eif_verify returns HALT
# ---------------------------------------------------------------------------

class EIFHaltError(Exception):
    """Raised when EIF HALT-routes one or more claims in a decision.

    Attributes:
        halt_cards: list of formatted markdown HALT cards (one per blocked claim).
        full_result: the complete eif_verify response dict.
    """

    def __init__(self, halt_cards: list[str], full_result: dict) -> None:
        self.halt_cards = halt_cards
        self.full_result = full_result
        summary = f"{len(halt_cards)} claim(s) HALT-routed"
        super().__init__(summary)

    def __str__(self) -> str:
        lines = [f"EIFHaltError: {len(self.halt_cards)} claim(s) HALT-routed\n"]
        for card in self.halt_cards:
            lines.append(card)
            lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# _run_eif_verify - calls the pipeline directly (bypasses MCP transport)
# ---------------------------------------------------------------------------

async def _run_eif_verify(
    session_id: str,
    decision: str,
    claims: list[dict] | None = None,
    conversation_turns: list[dict] | None = None,
    host_tool_outputs: list[dict] | None = None,
) -> dict:
    """Call the EIF pipeline directly without going through MCP.

    If `claims` is None, automatically extracts claims from the decision text
    using eif_extract_claims_from_decision.
    """
    if claims is None:
        from eif.mcp_server.server import eif_extract_claims_from_decision
        extracted = eif_extract_claims_from_decision(decision, max_claims=4)
        claims = extracted.get("claims", [])
        if not claims:
            _log.debug("eif_auto: no claims extracted from decision - returning PASS")
            return {"verdict": "PASS", "halted_claims": [], "halt_cards": [], "is_auto_pass": True}

    from eif.mcp_server.server import eif_verify
    return await eif_verify(
        session_id=session_id,
        decision=decision,
        claims=claims,
        conversation_turns=conversation_turns,
        host_tool_outputs=host_tool_outputs or [],
    )


# ---------------------------------------------------------------------------
# EIFSession - context manager
# ---------------------------------------------------------------------------

class EIFSession:
    """Context manager that holds a session_id and exposes a verify() method.

    Usage:
        async with EIFSession(session_id="s1") as guard:
            decision = await agent.run(task)
            await guard.verify(decision)
    """

    def __init__(
        self,
        session_id: str,
        raise_on_halt: bool = True,
        host_tool_outputs: list[dict] | None = None,
    ) -> None:
        self.session_id = session_id
        self.raise_on_halt = raise_on_halt
        self.host_tool_outputs = host_tool_outputs or []
        self._results: list[dict] = []

    async def __aenter__(self) -> EIFSession:
        from eif import session as session_store
        sess = await session_store.new_session(self.session_id)
        # The store assigns its own id (the caller's string is kept as the
        # linked_session_id); verification must use the store's id.
        self.session_id = sess.session_id
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        pass

    async def verify(
        self,
        decision: str,
        claims: list[dict] | None = None,
        conversation_turns: list[dict] | None = None,
    ) -> dict:
        """Run eif_verify on `decision`. Raises EIFHaltError if verdict is HALT."""
        result = await _run_eif_verify(
            session_id=self.session_id,
            decision=decision,
            claims=claims,
            conversation_turns=conversation_turns,
            host_tool_outputs=self.host_tool_outputs,
        )
        self._results.append(result)

        if result.get("verdict") == "HALT" and self.raise_on_halt:
            raise EIFHaltError(
                halt_cards=result.get("halt_cards", []),
                full_result=result,
            )
        return result

    @property
    def results(self) -> list[dict]:
        """All verification results accumulated in this session."""
        return self._results


# ---------------------------------------------------------------------------
# eif_guard - decorator
# ---------------------------------------------------------------------------

class eif_guard:  # noqa: N801 - intentional lowercase for decorator ergonomics
    """Decorator that wraps an async agent function and runs eif_verify on its output.

    Usage:
        @eif_guard(session_id="s1")
        async def decide(task: str) -> str:
            return await llm.complete(task)

    If the function returns a non-string (e.g. a dict), the decorator calls
    str() on it before extracting claims.

    Raises EIFHaltError if any claim is HALT-routed.
    """

    def __init__(
        self,
        session_id: str,
        claims: list[dict] | None = None,
        raise_on_halt: bool = True,
        host_tool_outputs: list[dict] | None = None,
    ) -> None:
        self.session_id = session_id
        self.claims = claims
        self.raise_on_halt = raise_on_halt
        self.host_tool_outputs = host_tool_outputs or []
        self._store_session_id: str | None = None

    def __call__(self, fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            output = await fn(*args, **kwargs)
            decision = output if isinstance(output, str) else str(output)
            if not self._store_session_id:
                from eif import session as session_store  # noqa: PLC0415
                sess = await session_store.new_session(self.session_id)
                self._store_session_id = sess.session_id
            result = await _run_eif_verify(
                session_id=self._store_session_id,
                decision=decision,
                claims=self.claims,
                host_tool_outputs=self.host_tool_outputs,
            )
            if result.get("verdict") == "HALT" and self.raise_on_halt:
                raise EIFHaltError(
                    halt_cards=result.get("halt_cards", []),
                    full_result=result,
                )
            return output
        return wrapper

    @staticmethod
    @asynccontextmanager
    async def session(
        session_id: str,
        raise_on_halt: bool = True,
        host_tool_outputs: list[dict] | None = None,
    ):
        """Convenience context manager. Equivalent to EIFSession(...)."""
        async with EIFSession(
            session_id=session_id,
            raise_on_halt=raise_on_halt,
            host_tool_outputs=host_tool_outputs,
        ) as s:
            yield s

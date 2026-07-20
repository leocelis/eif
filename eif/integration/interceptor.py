"""EIFInterceptor - LangChain callback handler for EIF verification.

Intercepts agent output at on_agent_finish and on_chain_end, extracts
decision text, runs eif_verify inline, and raises EIFHaltError if any
claim is HALT-routed.

Works with LangChain agents, chains, and LCEL pipelines. LangChain is an
optional dependency - importing this module without LangChain installed
raises ImportError with a clear install instruction.

Usage:

    from eif.integration.interceptor import EIFInterceptor, EIFHaltError

    interceptor = EIFInterceptor(session_id="s1")

    # With an agent executor:
    agent_executor = AgentExecutor(agent=agent, tools=tools,
                                   callbacks=[interceptor])

    # With an LCEL chain:
    chain = prompt | llm | output_parser
    chain.with_config(callbacks=[interceptor])

    try:
        result = await agent_executor.ainvoke({"input": task})
    except EIFHaltError as e:
        for card in e.halt_cards:
            print(card)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from eif.integration.eif_auto import EIFHaltError, _run_eif_verify

_log = logging.getLogger(__name__)


def _require_langchain() -> None:
    try:
        import langchain  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "LangChain is required to use EIFInterceptor. "
            "Install it with: pip install langchain"
        ) from exc


class EIFInterceptor:
    """LangChain BaseCallbackHandler that runs EIF verification on agent output.

    Intercepts two events:
      - on_agent_finish: fires when an AgentExecutor produces a final answer.
      - on_chain_end: fires when any chain (including LCEL) produces output.

    Only one event fires per agent invocation (whichever comes last). The
    interceptor deduplicates using the run_id so it does not double-verify.

    If verdict is HALT, raises EIFHaltError - LangChain propagates this as
    a normal exception from the ainvoke / invoke call.

    Constructor args:
        session_id:          EIF session ID (must be created with eif.session.new_session).
        claims:              Optional pre-extracted claims list. If None, claims are
                             auto-extracted from the output text using
                             eif_extract_claims_from_decision.
        raise_on_halt:       If True (default), raise EIFHaltError on HALT verdict.
                             If False, log a warning and continue.
        host_tool_outputs:   Optional pre-collected host tool results to use as P0 evidence.
        intercept_chains:    If True (default False), also intercept on_chain_end in addition
                             to on_agent_finish. Useful for non-agent LCEL pipelines.
    """

    def __init__(
        self,
        session_id: str,
        claims: list[dict] | None = None,
        raise_on_halt: bool = True,
        host_tool_outputs: list[dict] | None = None,
        intercept_chains: bool = False,
    ) -> None:
        _require_langchain()
        from langchain.callbacks.base import BaseCallbackHandler  # noqa: F401 - verify import

        self.session_id = session_id
        self.claims = claims
        self.raise_on_halt = raise_on_halt
        self.host_tool_outputs = host_tool_outputs or []
        self.intercept_chains = intercept_chains
        self._verified_run_ids: set[str] = set()
        self.last_result: dict | None = None

    def _build_base(self) -> Any:
        from langchain.callbacks.base import BaseCallbackHandler

        interceptor = self

        class _Handler(BaseCallbackHandler):
            def on_agent_finish(
                self,
                finish: Any,
                *,
                run_id: UUID,
                **kwargs: Any,
            ) -> None:
                run_key = str(run_id)
                if run_key in interceptor._verified_run_ids:
                    return
                interceptor._verified_run_ids.add(run_key)
                output_text = (
                    finish.return_values.get("output", "")
                    if hasattr(finish, "return_values")
                    else str(finish)
                )
                _run_sync_verify(interceptor, output_text)

            def on_chain_end(
                self,
                outputs: dict[str, Any],
                *,
                run_id: UUID,
                **kwargs: Any,
            ) -> None:
                if not interceptor.intercept_chains:
                    return
                run_key = str(run_id)
                if run_key in interceptor._verified_run_ids:
                    return
                interceptor._verified_run_ids.add(run_key)
                output_text = _extract_text(outputs)
                if output_text:
                    _run_sync_verify(interceptor, output_text)

        return _Handler()

    def __call__(self) -> Any:
        return self._build_base()

    def get_langchain_handler(self) -> Any:
        """Return the underlying LangChain BaseCallbackHandler instance."""
        return self._build_base()

    def __iter__(self):
        yield self._build_base()


def _extract_text(outputs: Any) -> str:
    """Best-effort extraction of decision text from a LangChain output value."""
    if isinstance(outputs, str):
        return outputs
    if isinstance(outputs, dict):
        for key in ("output", "text", "result", "answer", "response", "content"):
            if key in outputs:
                val = outputs[key]
                if isinstance(val, str):
                    return val
        return str(next(iter(outputs.values()), ""))
    return str(outputs)


def _run_sync_verify(interceptor: EIFInterceptor, decision: str) -> None:
    """Run eif_verify synchronously from a synchronous callback context."""
    try:
        asyncio.get_running_loop()
        # We are inside a running event loop (common in Jupyter / async frameworks).
        # Blocking this thread on a task scheduled on the same loop would
        # deadlock, so run the verification on a dedicated thread with its
        # own event loop and block on that thread instead.
        import concurrent.futures

        def _run_on_fresh_loop() -> dict:
            return asyncio.run(
                _run_eif_verify(
                    session_id=interceptor.session_id,
                    decision=decision,
                    claims=interceptor.claims,
                    host_tool_outputs=interceptor.host_tool_outputs,
                )
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_run_on_fresh_loop).result(timeout=60)

    except RuntimeError:
        # No event loop running - use asyncio.run directly.
        result = asyncio.run(
            _run_eif_verify(
                session_id=interceptor.session_id,
                decision=decision,
                claims=interceptor.claims,
                host_tool_outputs=interceptor.host_tool_outputs,
            )
        )

    interceptor.last_result = result
    _log.info(
        "EIFInterceptor verdict=%s session=%s halts=%d",
        result.get("verdict"),
        interceptor.session_id,
        len(result.get("halted_claims", [])),
    )

    if result.get("verdict") == "HALT":
        if interceptor.raise_on_halt:
            raise EIFHaltError(
                halt_cards=result.get("halt_cards", []),
                full_result=result,
            )
        else:
            _log.warning(
                "EIFInterceptor: HALT verdict (raise_on_halt=False). %d claim(s) blocked.",
                len(result.get("halted_claims", [])),
            )

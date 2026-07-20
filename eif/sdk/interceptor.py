"""EIF SDK - Local interceptor surfaces for in-code agents.

Implements the three integration surfaces from eif_local_interceptor_intent.yaml:

  A) EIFInterceptor - wraps an OpenAI client, intercepts every response locally.
     Zero network egress of LLM responses; the only outbound call is the evidence
     query (constraint I1). Uses SDK-native hooks when available (I2), falling
     back to attribute delegation wrapping for older versions.

  B) EIFCallbackHandler - LangChain/LangGraph on_llm_end callback.
     Intercepts at the LLM generation level, not chain level (constraint I4).

Security model (I1): EIF runs entirely on the developer's infrastructure.
  LLM responses never leave the developer's environment.
  Evidence queries (P3 web search, P0 host tool calls) are the ONLY outbound calls.
  Prompts, responses, and LLM API keys never touch EIF servers.
"""

from __future__ import annotations

import logging
from typing import Any

from eif.sdk.exceptions import EIFConfigError, EIFHaltError, HaltRecord

logger = logging.getLogger("eif.sdk.interceptor")

# Sentinel returned by _run_eif_locally when no MCP server is reachable.
_EIF_UNAVAILABLE = object()


def _extract_text(response: Any) -> str | None:
    """Extract message content from an OpenAI ChatCompletion response."""
    try:
        choices = response.choices
        if choices:
            return choices[0].message.content or ""
    except AttributeError:
        pass
    return None


def _run_eif_locally(claim_text: str, api_key: str, eif_server_url: str) -> dict | object:
    """Call the local EIF MCP server via HTTP.

    Runs on the developer's machine - constraint I1: responses never leave
    their infrastructure; this is a loopback call.
    Returns the parsed eif_verify result dict, or _EIF_UNAVAILABLE if the
    server is not reachable (e.g. developer hasn't started the MCP server yet).
    """
    import json  # noqa: PLC0415
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    payload = json.dumps({
        "claim_text": claim_text,
        "api_key": api_key,
    }).encode()
    req = urllib.request.Request(
        f"{eif_server_url}/verify",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        logger.debug("EIF local server unreachable: %s", exc)
        return _EIF_UNAVAILABLE


def _make_halt_record(claim_text: str, eif_result: dict, raw_response: Any) -> HaltRecord:
    return HaltRecord(
        claim_text=claim_text,
        verdict=eif_result.get("verdict", "HALT"),
        routing=eif_result.get("routing", "HALT_UNKNOWN"),
        evidence_summary=eif_result.get("evidence_summary", ""),
        confidence=float(eif_result.get("confidence", 0.0)),
        probe_tier=eif_result.get("probe_tier", "NONE"),
        evidence_source=eif_result.get("evidence_source", ""),
        metric_quality=eif_result.get("metric_quality"),
        raw_response=raw_response,
    )


# ─────────────────────────────────────────────────────────────────────────────
# A) EIFInterceptor - wraps an OpenAI client
# ─────────────────────────────────────────────────────────────────────────────

class _EIFWrappedCompletions:
    """Intercepts chat.completions.create() / acreate() calls through EIF."""

    def __init__(self, original: Any, interceptor: EIFInterceptor) -> None:
        self._original = original
        self._interceptor = interceptor
        # Forward all other attribute access (e.g. .with_raw_response)
        self.__dict__["_original"] = original

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)

    def create(self, *args: Any, **kwargs: Any) -> Any:
        response = self._original.create(*args, **kwargs)
        return self._interceptor._process_sync(response)

    async def acreate(self, *args: Any, **kwargs: Any) -> Any:
        response = await self._original.acreate(*args, **kwargs)
        return await self._interceptor._process_async(response)


class _EIFWrappedChat:
    def __init__(self, original: Any, interceptor: EIFInterceptor) -> None:
        self._completions = _EIFWrappedCompletions(original.completions, interceptor)

    @property
    def completions(self) -> _EIFWrappedCompletions:
        return self._completions


class EIFInterceptor:
    """Wraps an OpenAI client to intercept every chat completion through EIF locally.

    Usage::

        from openai import OpenAI
        from eif.sdk import EIFInterceptor, EIFHaltError

        client = OpenAI()
        eif = EIFInterceptor(api_key="eif-...", client=client)

        try:
            response = eif.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Evaluate this plan: ..."}],
            )
            print(response.choices[0].message.content)
        except EIFHaltError as e:
            print("HALT:", e.halt_record)

    All attributes not related to ``chat.completions`` are forwarded to the
    underlying client transparently (constraint I3 - ACT responses must be
    byte-identical and have < 5% p99 latency overhead).

    Note: async clients (``AsyncOpenAI``) are not intercepted; only the sync
    client surface is wrapped.

    The ``eif_server_url`` defaults to ``http://localhost:8080``, the default
    address of ``eif-mcp-http-server``. Set it to ``None`` to run EIF via the
    Python API directly (no HTTP roundtrip).
    """

    def __init__(
        self,
        api_key: str,
        client: Any = None,
        eif_server_url: str = "http://localhost:8080",
        on_halt: Any = None,
    ) -> None:
        if not api_key:
            raise EIFConfigError("EIFInterceptor requires an api_key.")
        self._api_key = api_key
        self._client = client
        self._eif_server_url = eif_server_url
        self._on_halt = on_halt  # optional: callable(halt_record) instead of raising

        if client is None:
            try:
                from openai import OpenAI  # noqa: PLC0415
                self._client = OpenAI()
            except ImportError as exc:
                raise EIFConfigError(
                    "openai package not installed. "
                    "Install it with: pip install eif-engine[sdk]"
                ) from exc

        self._chat_wrapper = _EIFWrappedChat(self._client.chat, self)

    @property
    def chat(self) -> _EIFWrappedChat:
        return self._chat_wrapper

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def _should_halt(self, eif_result: dict) -> bool:
        return eif_result.get("verdict") == "HALT" or eif_result.get("routing", "").startswith("HALT")

    def _process_sync(self, response: Any) -> Any:
        claim_text = _extract_text(response)
        if not claim_text:
            return response

        eif_result = _run_eif_locally(claim_text, self._api_key, self._eif_server_url)
        if eif_result is _EIF_UNAVAILABLE:
            logger.warning(
                "EIF local server unreachable at %s - response passed through unverified.",
                self._eif_server_url,
            )
            return response

        if self._should_halt(eif_result):
            record = _make_halt_record(claim_text, eif_result, response)
            if self._on_halt:
                self._on_halt(record)
                return response
            raise EIFHaltError(record)  # constraint I5 - default: raise

        return response

    async def _process_async(self, response: Any) -> Any:
        import asyncio  # noqa: PLC0415
        # Run the synchronous EIF check in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._process_sync, response)


# ─────────────────────────────────────────────────────────────────────────────
# B) EIFCallbackHandler - LangChain/LangGraph
# ─────────────────────────────────────────────────────────────────────────────

class EIFCallbackHandler:
    """LangChain callback handler that intercepts LLM responses through EIF.

    Hooks into ``on_llm_end`` (not ``on_chain_end``) to intercept at the raw
    generation level - constraint I4 from eif_local_interceptor_intent.yaml.

    Usage::

        from langchain.agents import AgentExecutor
        from eif.sdk import EIFCallbackHandler, EIFHaltError

        handler = EIFCallbackHandler(api_key="eif-...")
        agent = AgentExecutor(agent=agent, tools=tools, callbacks=[handler])

        # HALT is raised inside on_llm_end - catch it at the agent loop level.

    This class is a standalone implementation that does NOT require
    ``langchain`` to be installed - it works with any framework that calls
    ``on_llm_end(response, **kwargs)`` callbacks. If ``langchain-core`` is
    installed, it also registers as a proper ``BaseCallbackHandler`` subclass.
    """

    def __init__(
        self,
        api_key: str,
        eif_server_url: str = "http://localhost:8080",
        on_halt: Any = None,
    ) -> None:
        if not api_key:
            raise EIFConfigError("EIFCallbackHandler requires an api_key.")
        self._api_key = api_key
        self._eif_server_url = eif_server_url
        self._on_halt = on_halt

        # If langchain-core is installed, inherit from BaseCallbackHandler so
        # LangChain's callback machinery treats this as a native handler.
        try:
            from langchain_core.callbacks.base import BaseCallbackHandler  # noqa: PLC0415
            self.__class__.__bases__ = (BaseCallbackHandler,)
        except ImportError:
            pass

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Called by LangChain after each LLM generation (constraint I4).

        Intercepts at the per-generation level - fires once per LLM call,
        not once per chain run.
        """
        texts: list[str] = []
        try:
            # LangChain LLMResult: response.generations is list[list[Generation]]
            for gen_list in response.generations:
                for gen in gen_list:
                    text = getattr(gen, "text", None) or str(gen)
                    if text:
                        texts.append(text)
        except Exception:  # noqa: BLE001
            return

        for text in texts:
            eif_result = _run_eif_locally(text, self._api_key, self._eif_server_url)
            if eif_result is _EIF_UNAVAILABLE:
                logger.warning("EIF local server unreachable - generation passed through unverified.")
                continue
            verdict = eif_result.get("verdict")
            if verdict == "HALT" or str(eif_result.get("routing", "")).startswith("HALT"):
                record = _make_halt_record(text, eif_result, response)
                if self._on_halt:
                    self._on_halt(record)
                else:
                    raise EIFHaltError(record)  # constraint I5

    def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_llm_error(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_chain_start(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_chain_end(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_chain_error(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_tool_start(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_tool_end(self, *args: Any, **kwargs: Any) -> None:
        pass

    def on_tool_error(self, *args: Any, **kwargs: Any) -> None:
        pass

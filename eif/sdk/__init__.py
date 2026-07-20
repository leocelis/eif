"""EIF SDK - local interceptor surfaces for in-code agents.

Three integration surfaces (eif_local_interceptor_intent.yaml):

  A) EIFInterceptor   - wraps an OpenAI client; one line add to existing code.
  B) eif.auto         - import hook; zero-config, patches OpenAI at import time.
  C) EIFCallbackHandler - LangChain/LangGraph on_llm_end callback.

All surfaces run locally (constraint I1 - LLM responses never leave your infra).
HALT is surfaced as EIFHaltError by default (constraint I5).

Quick start::

    # A) Explicit wrapping
    from eif.sdk import EIFInterceptor, EIFHaltError
    client = OpenAI()
    eif = EIFInterceptor(api_key="eif-...", client=client)

    # B) Zero-config import hook (set EIF_API_KEY env var first)
    import eif.auto

    # C) LangChain
    from eif.sdk import EIFCallbackHandler
    agent = AgentExecutor(callbacks=[EIFCallbackHandler(api_key="eif-...")])
"""

from eif.sdk.exceptions import EIFConfigError, EIFHaltError, HaltRecord
from eif.sdk.interceptor import EIFCallbackHandler, EIFInterceptor

__all__ = [
    "EIFInterceptor",
    "EIFCallbackHandler",
    "EIFHaltError",
    "EIFConfigError",
    "HaltRecord",
]

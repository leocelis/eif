"""EIF integration layer - Python-native EIF without MCP.

Provides two integration patterns:

  1. EIFInterceptor (LangChain)
     A BaseCallbackHandler subclass that intercepts on_chain_end and
     on_agent_finish events, extracts decision text, and calls eif_verify.
     Raises EIFHaltError if any claim is HALT-routed.

     Usage:
         from eif.integration.interceptor import EIFInterceptor, EIFHaltError
         chain = my_chain.with_config(callbacks=[EIFInterceptor(session_id="s1")])

  2. eif_guard (generic decorator / context manager)
     Wraps any async function that returns a string decision.
     Can be used with AutoGen, CrewAI, custom agents, or any Python function.

     Usage:
         from eif.integration.eif_auto import eif_guard

         @eif_guard(session_id="s1")
         async def my_agent_decision(input: str) -> str:
             return await llm.generate(input)

         # or as a context manager:
         async with eif_guard.session("s1") as guard:
             result = await agent.run(task)
             await guard.verify(result)
"""

from eif.integration.eif_auto import EIFHaltError, eif_guard
from eif.integration.interceptor import EIFInterceptor

__all__ = ["EIFInterceptor", "eif_guard", "EIFHaltError"]

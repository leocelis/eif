"""Epistemic Integrity Framework (EIF).

Apply the scientific method to every load-bearing assumption an AI agent
makes: declare, falsify against independent evidence, calibrate a Bayesian
posterior, challenge adversarially, and route the result to ACT, REVISE,
or HALT.

Public surfaces:
    eif.session             - async session store
    eif.schemas             - Pydantic v2 models (dependency root)
    eif.mcp_server.server   - MCP server exposing the 24 pipeline tools
    eif.sdk                 - EIFInterceptor / EIFCallbackHandler / EIFHaltError
    eif.auto                - zero-config import hook (import eif.auto)
    eif.integration         - in-process interceptor (no HTTP server needed)
"""

from __future__ import annotations

from eif.schemas import ENGINE_VERSION

__version__ = ENGINE_VERSION

__all__ = ["ENGINE_VERSION", "__version__"]

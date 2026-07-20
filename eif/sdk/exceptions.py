"""EIF SDK exceptions - surfacing HALT verdicts to calling code.

Implements constraint I5 from eif_local_interceptor_intent.yaml:
  When EIF routes a response to HALT, the developer's calling code must receive
  a signal it can act on. Default behavior: raise EIFHaltError.

Backward-compatibility note:
  eif.integration.eif_auto.EIFHaltError is the original in-process exception
  (carries halt_cards: list[str] and full_result: dict - used by the LangChain
  interceptor and eif_guard).

  EIFHaltError here (in eif.sdk) is the external-HTTP-server exception used by
  EIFInterceptor (wraps an OpenAI client that calls localhost:8080/verify).
  It carries a structured HaltRecord dataclass instead of raw card strings.

  The two are intentionally separate because:
    eif.integration  - in-process, calls eif_verify pipeline directly, needs a session
    eif.sdk          - external, wraps any OpenAI client, calls the HTTP MCP server

  The canonical import for each use case:
    In-process (LangChain / eif_guard):  from eif.integration import EIFHaltError
    OpenAI client wrap / eif.auto:       from eif.sdk import EIFHaltError
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HaltRecord:
    """Structured payload attached to an EIFHaltError (eif.sdk).

    Fields mirror the HALT routing response produced by the EIF HTTP server
    (eif-mcp-http-server running at localhost:8080).
    """
    claim_text: str
    verdict: str                        # HALT | ACT
    routing: str                        # routing label (e.g. "HALT_GUESSED_CLAIM")
    evidence_summary: str
    confidence: float
    probe_tier: str                     # P0–P4 or "NONE"
    evidence_source: str
    metric_quality: str | None = None   # F17 signal if evidence was degraded
    raw_response: Any = None            # the original LLM response object, if available
    extra: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"EIF HALT - {self.routing}\n"
            f"  Claim:    {self.claim_text[:120]}\n"
            f"  Evidence: {self.evidence_summary[:120]}\n"
            f"  Tier:     {self.probe_tier} / {self.evidence_source}\n"
            f"  Confidence: {self.confidence:.2f}"
            + (f"\n  metric_quality: {self.metric_quality}" if self.metric_quality else "")
        )


class EIFHaltError(Exception):
    """Raised by EIF SDK interceptors (eif.sdk) when a HALT verdict is reached.

    Use this when integrating via EIFInterceptor (OpenAI client wrapper) or
    eif.auto. The halt_record attribute contains the full HALT record.

    For in-process LangChain integration, use eif.integration.EIFHaltError
    instead - it carries halt_cards (list[str]) from the eif_verify pipeline.

    Example::

        from eif.sdk import EIFInterceptor, EIFHaltError

        client = OpenAI()
        eif = EIFInterceptor(api_key="eif-...", client=client)
        try:
            response = eif.chat.completions.create(model="gpt-4o", messages=[...])
        except EIFHaltError as e:
            print(f"HALT: {e.halt_record}")
    """

    def __init__(self, halt_record: HaltRecord) -> None:
        self.halt_record = halt_record
        super().__init__(str(halt_record))


class EIFConfigError(Exception):
    """Raised when EIF SDK is misconfigured (missing API key, invalid options)."""

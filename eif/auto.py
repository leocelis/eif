"""eif.auto - zero-config EIF interceptor import hook.

Add a single line to your agent's entry point::

    import eif.auto

EIF will automatically intercept every OpenAI (and optionally Anthropic) LLM
response and run eif_verify locally - before the response reaches your code.

Pattern inspired by ``import ddtrace.auto`` (Datadog APM zero-config hook).
Reference: eif_local_interceptor_intent.yaml §solution.B

Security model (constraint I1): interception runs entirely on the developer's
machine. LLM responses never leave their infrastructure. The only outbound
call is the evidence query (P3 web search, P0 host tool call) - read-only.

Configuration via environment variables::

    EIF_API_KEY          Required. Your EIF API key.
    EIF_SERVER_URL       Optional. Default: http://localhost:8080
    EIF_HALT_MODE        Optional. "raise" (default) | "log" | "callback"
    EIF_LOG_LEVEL        Optional. Default: WARNING

For more control, use EIFInterceptor or EIFCallbackHandler directly:
    from eif.sdk import EIFInterceptor, EIFCallbackHandler
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("eif.auto")

_api_key = os.environ.get("EIF_API_KEY", "")
_server_url = os.environ.get("EIF_SERVER_URL", "http://localhost:8080")
_halt_mode = os.environ.get("EIF_HALT_MODE", "raise")


def _make_on_halt(mode: str):
    """Build the on_halt callback based on EIF_HALT_MODE."""
    from eif.sdk.exceptions import HaltRecord  # noqa: PLC0415

    if mode == "log":
        def _log_halt(record: HaltRecord) -> None:
            logger.warning("EIF HALT (log mode - not raising): %s", record)
        return _log_halt

    if mode == "callback":
        # For future extension: users can register a custom callback at
        # eif.auto.on_halt = my_function after importing eif.auto.
        return getattr(sys.modules[__name__], "on_halt", None)

    return None  # "raise" mode: pass None → EIFHaltError raised by default


def _patch_openai() -> bool:
    """Monkey-patch the OpenAI SDK to route all chat completions through EIF.

    Uses attribute delegation wrapping on the OpenAI class - no private method
    access. Works with openai >= 1.0.

    Returns True if patching succeeded, False if openai is not installed.
    """
    try:
        import openai  # noqa: PLC0415
    except ImportError:
        return False

    from eif.sdk.interceptor import EIFInterceptor, _EIFWrappedChat  # noqa: PLC0415

    if getattr(openai.OpenAI, "_eif_patched", False):
        return True
    openai.OpenAI._eif_patched = True  # type: ignore[attr-defined]
    _original_init = openai.OpenAI.__init__

    def _patched_init(self, *args, **kwargs):  # type: ignore[override]
        _original_init(self, *args, **kwargs)
        # Wrap the chat property with EIF interception
        _interceptor = EIFInterceptor(
            api_key=_api_key,
            client=self,
            eif_server_url=_server_url,
            on_halt=_make_on_halt(_halt_mode),
        )
        # Replace the .chat property with an EIF-wrapped version
        object.__setattr__(self, "_eif_chat_wrapper", _EIFWrappedChat(self.chat, _interceptor))
        _original_chat_property = type(self).chat

        def _eif_chat_getter(inner_self):  # type: ignore[misc]
            return getattr(inner_self, "_eif_chat_wrapper", None) or _original_chat_property.__get__(inner_self)

        type(self).chat = property(_eif_chat_getter)  # type: ignore[assignment]

    openai.OpenAI.__init__ = _patched_init  # type: ignore[method-assign]
    logger.debug("eif.auto: OpenAI SDK patched.")
    return True


def _patch_anthropic() -> bool:
    """Best-effort monkey-patch for the Anthropic SDK.

    Anthropic does not have a native interceptor API (as of 2026-05).
    This wraps messages.create() via attribute delegation.
    Labeled 'best-effort' per eif_local_interceptor_intent.yaml §OI2:
    not guaranteed across Anthropic SDK version updates.
    Returns True if patching succeeded, False if anthropic is not installed.
    """
    try:
        import anthropic  # noqa: PLC0415
    except ImportError:
        return False

    from eif.sdk.exceptions import EIFHaltError  # noqa: PLC0415
    from eif.sdk.interceptor import _make_halt_record, _run_eif_locally  # noqa: PLC0415

    # Anthropic client: .messages.create() is the main entry point
    class _EIFAnthropicMessages:
        def __init__(self, original):
            self._original = original

        def __getattr__(self, name):
            return getattr(self._original, name)

        def create(self, *args, **kwargs):
            response = self._original.create(*args, **kwargs)
            text = ""
            try:
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text
            except Exception:  # noqa: BLE001
                return response

            if not text:
                return response

            eif_result = _run_eif_locally(text, _api_key, _server_url)
            from eif.sdk.interceptor import _EIF_UNAVAILABLE  # noqa: PLC0415
            if eif_result is _EIF_UNAVAILABLE:
                logger.warning("EIF local server unreachable - Anthropic response unverified.")
                return response

            if eif_result.get("verdict") == "HALT":
                record = _make_halt_record(text, eif_result, response)
                on_halt = _make_on_halt(_halt_mode)
                if on_halt:
                    on_halt(record)
                else:
                    raise EIFHaltError(record)
            return response

    if getattr(anthropic.Anthropic, "_eif_patched", False):
        return True
    anthropic.Anthropic._eif_patched = True  # type: ignore[attr-defined]
    _original_anthropic_init = anthropic.Anthropic.__init__

    def _patched_anthropic_init(self, *args, **kwargs):  # type: ignore[override]
        _original_anthropic_init(self, *args, **kwargs)
        self._eif_messages_wrapper = _EIFAnthropicMessages(self.messages)
        type(self).messages = property(lambda s: s._eif_messages_wrapper)  # type: ignore[assignment]

    anthropic.Anthropic.__init__ = _patched_anthropic_init  # type: ignore[method-assign]
    logger.debug("eif.auto: Anthropic SDK patched (best-effort).")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Apply patches at import time
# ─────────────────────────────────────────────────────────────────────────────

if not _api_key:
    logger.warning(
        "eif.auto imported but EIF_API_KEY is not set. "
        "Set EIF_API_KEY to match your self-hosted server's key "
        "(or leave the server in development mode and set any value)."
    )

_openai_patched = _patch_openai()
_anthropic_patched = _patch_anthropic()

if _openai_patched or _anthropic_patched:
    patched = []
    if _openai_patched:
        patched.append("openai")
    if _anthropic_patched:
        patched.append("anthropic (best-effort)")
    logger.info(
        "eif.auto active - EIF intercepting %s locally. "
        "Server: %s. Halt mode: %s.",
        " + ".join(patched),
        _server_url,
        _halt_mode,
    )

# Public hook: override at runtime after `import eif.auto`
# Example: eif.auto.on_halt = lambda r: print(f"HALT: {r}")
on_halt = None

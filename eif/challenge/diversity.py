"""Classify critic independence level from model identifier string."""

from __future__ import annotations

from eif.schemas import CriticIndependence

_GPT_FAMILY = {"gpt", "o1", "o3", "chatgpt", "openai"}
_CLAUDE_FAMILY = {"claude", "anthropic"}
_GEMINI_FAMILY = {"gemini", "bard", "google"}
_LLAMA_FAMILY = {"llama", "meta", "mistral", "mixtral"}

_SELF_CONSISTENCY_MARKERS = {"self-consistency", "self_consistency", "sampling", "majority-vote"}
_OBJECTIVE_MARKERS = {"fine-tuned", "fine_tuned", "finetuned", "flaw", "critic", "adversarial", "red-team"}


def classify_independence(critic_model: str | None) -> CriticIndependence:
    """Classify the independence level of a critic model.

    Heuristic:
    - DIFFERENT_FAMILY: critic is from a different model family (GPT vs Claude, etc.)
    - DIFFERENT_INFERENCE: self-consistency or sampling-based critic
    - DIFFERENT_OBJECTIVE: fine-tuned for flaw-finding or adversarial critique
    - NONE: no critic model provided
    """
    if critic_model is None:
        return "NONE"

    model_lower = critic_model.lower()

    for marker in _OBJECTIVE_MARKERS:
        if marker in model_lower:
            return "DIFFERENT_OBJECTIVE"

    for marker in _SELF_CONSISTENCY_MARKERS:
        if marker in model_lower:
            return "DIFFERENT_INFERENCE"

    # Detect cross-family: check if model belongs to a different family than the agent
    # We default to assuming the agent is Claude-based; if critic is GPT/Gemini/Llama = DIFFERENT_FAMILY
    families_present = set()
    for family_name, markers in [
        ("gpt", _GPT_FAMILY),
        ("claude", _CLAUDE_FAMILY),
        ("gemini", _GEMINI_FAMILY),
        ("llama", _LLAMA_FAMILY),
    ]:
        if any(m in model_lower for m in markers):
            families_present.add(family_name)

    if len(families_present) > 0:
        # Model string matches a known family → DIFFERENT_FAMILY.
        # Note: multi_critic.py appends _ADVERSARIAL_SUFFIX ("-adversarial-critic") to the
        # independence_label before calling this function, so DIFFERENT_OBJECTIVE is matched
        # first (L30–32) for any configured critic model, overriding DIFFERENT_FAMILY.
        return "DIFFERENT_FAMILY"

    # Unknown model and no adversarial/objective markers - independence cannot be determined.
    return "NONE"

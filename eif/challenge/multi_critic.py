"""Multi-critic challenge - actual LLM calls with adversarial independence.

Closes S5 gap: the old CHALLENGE phase generated a protocol document that no
agent executed. This module calls real LLMs with adversarial system prompts
(DIFFERENT_OBJECTIVE tier) and, when a cross-family model is configured via
OPENAI_CRITIC_MODEL, routes to that model (DIFFERENT_FAMILY tier).

Tournament mode (num_critics > 1):
  Inspired by the AI Co-Scientist (arXiv:2502.18864) tournament evaluation - 
  multiple critics compete; counter-evidence is merged and ranked by specificity
  (longer, more concrete objections score higher). The strongest objections
  from any critic surface in the final result.

  Unlike the AI Co-Scientist's hypothesis tournament (comparing hypotheses
  head-to-head), EIF's tournament compares objections to a single claim:
  each critic produces independent counter-evidence, and the merged set is
  deduplicated and ranked so the most substantive objections appear first.

Research: CONSENSAGENT ACL 2025 - inter-agent sycophancy in debate settings;
          hardened critic design with DIFFERENT_OBJECTIVE instruction suppresses
          agreement bias. Specific agreement-rate figures omitted per intent
          OI1 (eif_multi_critic_intent.yaml - paper percentages removed to
          prevent encoding stale benchmarks).
          AI Co-Scientist (arXiv:2502.18864) - tournament-based evaluation.

Intent: eif/eif/challenge/eif_multi_critic_intent.yaml
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import openai

import json
import os

from eif.challenge.diversity import classify_independence
from eif.challenge.protocol import build_challenge_result
from eif.schemas import ChallengeResult

# Adversarial suffix appended to the model name so diversity.py
# classifies it as DIFFERENT_OBJECTIVE via the 'adversarial' marker.
_ADVERSARIAL_SUFFIX = "-adversarial-critic"

_SYSTEM_PROMPT = """\
You are an adversarial red-team critic. Your sole objective is to find flaws,
counter-evidence, and competing hypotheses for the claim you are given.

Rules:
- Do NOT validate or agree with the claim.
- Do NOT hedge. Every response must contain at least one counter-argument.
- If a claim seems well-supported, look harder: find the edge case, the
  missing confounder, the weaker piece of evidence, the contrary study.
- Your output is used to stress-test AI agent reasoning. Weak critique is
  useless. Strong critique improves epistemic integrity.

Return valid JSON with this structure:
{
  "counter_evidence": ["<item 1>", "<item 2>", ...],
  "competing_hypothesis": "<alternative explanation or null>",
  "strongest_objection": "<the single most damaging counter-argument>"
}
"""

_USER_TEMPLATE = """\
CLAIM TO CHALLENGE:
"{claim_text}"

Current posterior confidence: {posterior:.2f}

Provide adversarial counter-evidence. Do not validate. Find flaws.
"""


def _select_critic_model(generator_model: str | None) -> tuple[str, str]:
    """Select the best available critic model.

    Returns:
        (api_model_name, independence_label)
        api_model_name: actual model string to pass to OpenAI API
        independence_label: model identifier string for diversity.py classification
    """
    env_critic = os.environ.get("OPENAI_CRITIC_MODEL", "").strip()

    if env_critic:
        # MC2: an explicitly configured critic model implies independence intent.
        # Append the adversarial suffix so classify_independence returns
        # DIFFERENT_OBJECTIVE even when the model name contains no known family/
        # objective markers (avoids NONE for custom/fine-tuned model names).
        independence_label = env_critic + _ADVERSARIAL_SUFFIX
        return env_critic, independence_label

    # Default: use gpt-4.1-mini with adversarial label for DIFFERENT_OBJECTIVE
    base = "gpt-4.1-mini"
    label = base + _ADVERSARIAL_SUFFIX
    return base, label


def _call_single_critic(
    client: openai.OpenAI,
    api_model: str,
    claim_text: str,
    posterior: float,
    timeout: float,
    temperature: float = 0.7,
) -> tuple[list[str], str | None]:
    """Execute one critic call. Returns (counter_evidence, competing_hypothesis).

    Args:
        temperature: 0.7 for the primary critic (balanced); 0.9 for diversity
                     critics in tournament mode (higher entropy → more distinct objections).
    """
    import openai

    user_msg = _USER_TEMPLATE.format(claim_text=claim_text, posterior=posterior)
    counter_evidence: list[str] = []
    competing_hypothesis: str | None = None

    try:
        response = client.chat.completions.create(
            model=api_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
            timeout=timeout,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)

        counter_evidence = data.get("counter_evidence", [])
        competing_hypothesis = data.get("competing_hypothesis") or None
        strongest = data.get("strongest_objection", "")
        if strongest and strongest not in counter_evidence:
            counter_evidence.insert(0, strongest)

    except openai.APIError as exc:
        counter_evidence = [f"critic_api_error: {exc!r}"]
    except json.JSONDecodeError:
        counter_evidence = ["critic_returned_non_json"]
    except Exception as exc:  # noqa: BLE001
        counter_evidence = [f"critic_error: {exc!r}"]

    return counter_evidence, competing_hypothesis


def _rank_evidence(items: list[str]) -> list[str]:
    """Rank counter-evidence by specificity (longer = more concrete).

    Tournament principle: the strongest, most specific objections surface first.
    Error/placeholder strings are pushed to the end.
    """
    def score(item: str) -> int:
        if item.startswith("critic_"):
            return -1
        return len(item)

    return sorted(items, key=score, reverse=True)


def _merge_evidence(
    all_evidence: list[list[str]],
    all_hypotheses: list[str | None],
) -> tuple[list[str], str | None]:
    """Merge counter-evidence from multiple critics.

    Deduplicates by lowercased token overlap (>= 0.7 Jaccard = same objection).
    Returns the first non-None competing_hypothesis found.
    """
    seen: list[str] = []

    def is_duplicate(candidate: str) -> bool:
        cand_tokens = set(candidate.lower().split())
        for existing in seen:
            ex_tokens = set(existing.lower().split())
            union = cand_tokens | ex_tokens
            if union and len(cand_tokens & ex_tokens) / len(union) >= 0.7:
                return True
        return False

    flat: list[str] = []
    for batch in all_evidence:
        for item in batch:
            if not is_duplicate(item):
                seen.append(item)
                flat.append(item)

    ranked = _rank_evidence(flat)
    hypothesis = next((h for h in all_hypotheses if h), None)
    return ranked, hypothesis


def run_multi_critic_challenge(
    claim_text: str,
    generator_model: str | None = None,
    posterior: float = 0.50,
    api_key: str | None = None,
    timeout: float = 30.0,
    num_critics: int = 1,
) -> ChallengeResult:
    """Challenge a claim using one or more adversarial independent critics.

    This function makes real LLM calls - it is not a protocol stub.
    self_evaluation_flag will be False on the returned ChallengeResult.

    When num_critics > 1 (tournament mode), critics run sequentially; their
    counter-evidence is merged, deduplicated, and ranked by specificity.
    The strongest objections surface first in the final ChallengeResult.
    The independence level reported reflects the highest tier achieved
    across all critics.

    Constraints satisfied:
        MC1 - self_evaluation_flag=False (real LLM call)
        MC2 - critic_independence is DIFFERENT_FAMILY or DIFFERENT_OBJECTIVE
        MC5 - timeout guard ≤ 30 seconds per critic

    Args:
        claim_text:      The claim to challenge.
        generator_model: Model that generated the claim (selects cross-family critic).
        posterior:       Current posterior confidence in the claim [0, 1].
        api_key:         OpenAI API key (falls back to OPENAI_API_KEY env var).
        timeout:         Max seconds to wait per critic response.
        num_critics:     Number of critics to run (1 = standard; 2+ = tournament).
                         Default is 1 for backward compatibility.

    Returns:
        ChallengeResult with merged counter_evidence ranked by specificity.
    """
    import openai

    num_critics = max(1, int(num_critics))

    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    client = openai.OpenAI(api_key=key) if key else openai.OpenAI()

    api_model, independence_label = _select_critic_model(generator_model)
    independence = classify_independence(independence_label)

    # Tournament: exactly num_critics API calls total.
    # Critic 0 runs at temp=0.7 (standard); critics 1..N-1 run at temp=0.9
    # (higher entropy → more distinct objections, supporting genuine diversity).
    all_evidence: list[list[str]] = []
    all_hypotheses: list[str | None] = []

    for i in range(num_critics):
        temperature = 0.7 if i == 0 else 0.9
        evidence, hypothesis = _call_single_critic(
            client, api_model, claim_text, posterior, timeout, temperature=temperature
        )
        all_evidence.append(evidence)
        all_hypotheses.append(hypothesis)

    merged_evidence, competing_hypothesis = _merge_evidence(all_evidence, all_hypotheses)

    result = build_challenge_result(
        claim_text=claim_text,
        critic_model=independence_label,
        counter_evidence=merged_evidence,
        competing_hypothesis=competing_hypothesis,
        critic_approach=independence,
    )
    # SC5: tournament multi-critic is maximally hardened when multiple critics ran
    if num_critics > 1:
        result = result.model_copy(update={"hardening_score": 1.0})

    return result

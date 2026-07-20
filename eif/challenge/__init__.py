"""EIF Phase 4 - CHALLENGE: adversarial probe of claims.

v3 adds run_multi_critic_challenge - closes S5 gap (multi-agent parametric
diversity). The old build_challenge_result() / generate_protocol() remain
unchanged for backward compatibility (constraint MC6).
"""

from eif.challenge.diversity import classify_independence
from eif.challenge.multi_critic import run_multi_critic_challenge
from eif.challenge.protocol import build_challenge_result, generate_protocol

__all__ = [
    "classify_independence",
    "build_challenge_result",
    "generate_protocol",
    "run_multi_critic_challenge",
]

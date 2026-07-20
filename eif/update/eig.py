"""Expected Information Gain (EIG) computation.

EIG = KL(posterior ∥ prior) = p*log(p/q) + (1-p)*log((1-p)/(1-q))

where p = posterior, q = prior.

Edge cases handled with epsilon=1e-10 to avoid log(0).
"""

from __future__ import annotations

import math

_EPS = 1e-10


def compute_eig(prior: float, posterior: float) -> float:
    """Compute Expected Information Gain: KL(Ber(posterior) ∥ Ber(prior)).

    KL(posterior ∥ prior) = p*log(p/q) + (1-p)*log((1-p)/(1-q))
    where p = posterior, q = prior.

    Returns 0.0 when prior and posterior are equal (no information gained).
    """
    p = max(_EPS, min(1 - _EPS, posterior))
    q = max(_EPS, min(1 - _EPS, prior))

    kl = p * math.log(p / q) + (1 - p) * math.log((1 - p) / (1 - q))
    return max(0.0, kl)

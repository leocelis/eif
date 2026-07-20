"""EIF v2 - SYCOPHANCY_GATE module.

Detects four sycophancy signals in agent responses:
  S1: Agreement-before-evidence (Wei et al. 2023 arXiv:2308.03958)
  S2: Position drift across turns (Truth Decay 2025 arXiv:2503.11656)
  S3: Unfaithful CoT (Turpin et al. NeurIPS 2023 arXiv:2305.04388)
  S4: Face-preserving framing on HALT turns (ELEPHANT 2025 arXiv:2505.13995)

Research: eif/research/sycophancy_bias_research.md
Intent:   eif/eif/sycophancy/eif_sycophancy_intent.yaml
"""

from eif.sycophancy.cost_model import CostModel, build_cost_model
from eif.sycophancy.detector import SycophancyGate, SycophancyResult
from eif.sycophancy.drift import PositionRecord, PositionRegister

__all__ = [
    "SycophancyGate",
    "SycophancyResult",
    "PositionRecord",
    "PositionRegister",
    "CostModel",
    "build_cost_model",
]

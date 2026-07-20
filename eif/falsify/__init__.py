"""EIF Phase 2 - FALSIFY: define and test falsification conditions."""

from eif.falsify.condition import build_condition
from eif.falsify.sprt import run_sprt
from eif.falsify.trivial_check import is_trivial

__all__ = ["build_condition", "run_sprt", "is_trivial"]

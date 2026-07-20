"""EIF Phase 5.5 - EXPLAIN: hard-to-vary explanation validation."""

from eif.explain.artifact import build_artifact
from eif.explain.hard_to_vary import check_hard_to_vary
from eif.explain.reach import classify_reach

__all__ = ["check_hard_to_vary", "build_artifact", "classify_reach"]

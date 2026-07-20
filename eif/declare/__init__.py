"""EIF Phase 1 - DECLARE: name and classify every assumption."""

from eif.declare.harking_guard import detect_harking
from eif.declare.registry import build_registry

__all__ = ["build_registry", "detect_harking"]

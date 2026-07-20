"""EIF Phase 8 - PROGRAMME: Lakatos research programme health assessment."""

from eif.programme.monitor import compute_status
from eif.programme.signals import compute_signals
from eif.programme.status import derive_status_text

__all__ = ["compute_signals", "compute_status", "derive_status_text"]

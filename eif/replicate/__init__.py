"""EIF Phase 7 - REPLICATE: replication protocol and divergence analysis."""

from eif.replicate.divergence import evaluate_replication
from eif.replicate.protocol import generate_replication_protocol

__all__ = ["generate_replication_protocol", "evaluate_replication"]

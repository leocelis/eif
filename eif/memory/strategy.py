"""EvoScientist-inspired cross-session strategic memory for EIF.

Persists learnings from past sessions so future sessions can benefit from
what evidence tiers worked, which domains triggered systematic HALTs, and
which falsification strategies were most discriminative.

Design (EvoScientist, arXiv:2603.08127):
  - Two memory types: Ideation Strategy Memory and Experimentation Strategy Memory.
  - EIF analogue: "what claim types and domains lead to HALTs?" (ideation) and
    "which evidence tiers were most informative for which domains?" (experimentation).

Storage:
  ~/.eif/strategy_memory.json - JSON file, created automatically.
  Override via EIF_MEMORY_PATH environment variable.

Schema per domain key:
  {
    "sessions_seen": int,
    "halt_rate": float,               # fraction of sessions ending in HALT
    "evidence_tier_hits": {           # which P-tier was most often decisive
        "P0": int, "P1": int, "P2": int, "P3": int, "P4": int
    },
    "common_halt_reasons": list[str], # top-3 HALT trigger patterns
    "avg_final_posterior": float,     # mean posterior at session end
    "paradigm_alerts_fired": int,     # how often PIEVO alert fired in this domain
  }

Usage:
    from eif.memory.strategy import load_strategy_memory

    mem = load_strategy_memory()
    mem.record_session(
        domain="healthcare",
        final_route="HALT",
        decisive_tier="P2",
        halt_reason="CAUSAL_UNVERIFIED",
        final_posterior=0.18,
        paradigm_alert=False,
    )
    tip = mem.get_tip("healthcare")
    # Returns a plain-language string: "In healthcare, P2 is most often decisive.
    #  HALT rate is 62%. Consider running the causal gate early."

Research: EvoScientist (arXiv:2603.08127, 2026) - persistent strategy memory
across research cycles. The Evolution Manager distills insights into memory
modules that the Researcher and Engineer read at the start of each new cycle.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

_DEFAULT_MEMORY_PATH = Path.home() / ".eif" / "strategy_memory.json"
_MAX_HALT_REASONS = 10       # max stored halt reasons per domain
_TOP_HALT_REASONS = 3        # how many to surface in tip

_EMPTY_DOMAIN: dict[str, Any] = {
    "sessions_seen": 0,
    "halt_rate": 0.0,
    "halt_count": 0,
    "evidence_tier_hits": {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "P4": 0},
    "common_halt_reasons": [],
    "avg_final_posterior": 0.5,
    "posterior_sum": 0.0,
    "paradigm_alerts_fired": 0,
}


class StrategyMemory:
    """Cross-session strategic knowledge store for EIF.

    Thread-safety: single-process only. For concurrent use, wrap with a lock.
    """

    def __init__(self, path: Path | None = None) -> None:
        env_path = os.environ.get("EIF_MEMORY_PATH", "")
        self._path: Path = Path(env_path) if env_path else (path or _DEFAULT_MEMORY_PATH)
        self._data: dict[str, Any] = self._load()

    # ─────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────

    def record_session(
        self,
        domain: str,
        final_route: str,
        decisive_tier: str | None = None,
        halt_reason: str | None = None,
        final_posterior: float = 0.5,
        paradigm_alert: bool = False,
    ) -> None:
        """Record outcomes of a completed EIF session into the strategy memory.

        Args:
            domain:           Free-form domain string inferred by eif_record's _infer_domain()
                              logic. Common values: "healthcare", "hipaa_compliance", "finance",
                              "legal", "engineering", "generic". Not restricted to DomainKey enum
                              in cost_model.py - strategy memory accepts any string key.
            final_route:      Final routing decision: "ACT", "REVISE", or "HALT"
            decisive_tier:    Evidence tier that drove the final verdict: "P1"–"P4"
            halt_reason:      Short reason code when final_route == "HALT"
                              (e.g. "CAUSAL_UNVERIFIED", "S2_DRIFT_FORCE_HALT")
            final_posterior:  Posterior probability at session end
            paradigm_alert:   True if a ParadigmRevisionAlert fired in this session
        """
        d = self._domain(domain)

        d["sessions_seen"] += 1
        d["posterior_sum"] += final_posterior
        d["avg_final_posterior"] = d["posterior_sum"] / d["sessions_seen"]

        if final_route == "HALT":
            d["halt_count"] += 1
        d["halt_rate"] = d["halt_count"] / d["sessions_seen"]

        if decisive_tier and decisive_tier in d["evidence_tier_hits"]:
            d["evidence_tier_hits"][decisive_tier] += 1

        if halt_reason:
            reasons: list[str] = d["common_halt_reasons"]
            reasons.append(halt_reason)
            # Keep only the most recent _MAX_HALT_REASONS entries
            d["common_halt_reasons"] = reasons[-_MAX_HALT_REASONS:]

        if paradigm_alert:
            d["paradigm_alerts_fired"] += 1

        self._data[domain] = d
        self._save()

    def get_tip(self, domain: str) -> str | None:
        """Return a plain-language strategy tip for the given domain.

        Returns None if fewer than 3 sessions have been seen (insufficient data).
        """
        d = self._data.get(domain)
        if not d or d.get("sessions_seen", 0) < 3:
            return None

        lines: list[str] = []

        # Best evidence tier
        tier_hits: dict[str, int] = d.get("evidence_tier_hits", {})
        best_tier = max(tier_hits, key=lambda k: tier_hits[k]) if tier_hits else None
        if best_tier and tier_hits[best_tier] > 0:
            lines.append(
                f"In {domain}, {best_tier} evidence has been most decisive "
                f"({tier_hits[best_tier]} / {d['sessions_seen']} sessions)."
            )

        # HALT rate
        halt_rate = d.get("halt_rate", 0.0)
        if halt_rate > 0.4:
            lines.append(
                f"HALT rate is {halt_rate:.0%} - consider running INPUT_GUARD and "
                "CAUSAL_GATE early to catch likely failures before the full pipeline."
            )

        # Common HALT reasons
        reasons: list[str] = d.get("common_halt_reasons", [])
        if reasons:
            top = [item for item, _ in Counter(reasons).most_common(_TOP_HALT_REASONS)]
            lines.append(f"Most common HALT triggers: {', '.join(top)}.")

        # Paradigm alerts
        alerts = d.get("paradigm_alerts_fired", 0)
        if alerts > 0 and d["sessions_seen"] > 0:
            alert_rate = alerts / d["sessions_seen"]
            if alert_rate > 0.3:
                lines.append(
                    f"Paradigm revision alerts fired in {alert_rate:.0%} of sessions - "
                    "revisit claim framing in DECLARE before committing to FALSIFY."
                )

        return " ".join(lines) if lines else None

    def get_all_tips(self) -> dict[str, str]:
        """Return tips for all domains with enough data."""
        return {
            domain: tip
            for domain in self._data
            if (tip := self.get_tip(domain)) is not None
        }

    def domain_stats(self, domain: str) -> dict[str, Any] | None:
        """Return raw stats for a domain, or None if not seen."""
        d = self._data.get(domain)
        if not d:
            return None
        return {
            "sessions_seen": d["sessions_seen"],
            "halt_rate": round(d["halt_rate"], 3),
            "best_evidence_tier": max(
                d["evidence_tier_hits"], key=lambda k: d["evidence_tier_hits"][k]
            ) if any(d["evidence_tier_hits"].values()) else None,
            "avg_final_posterior": round(d["avg_final_posterior"], 3),
            "paradigm_alerts_fired": d["paradigm_alerts_fired"],
        }

    # ─────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────

    def _domain(self, domain: str) -> dict[str, Any]:
        if domain not in self._data:
            import copy
            self._data[domain] = copy.deepcopy(_EMPTY_DOMAIN)
        return self._data[domain]

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                _log.warning("StrategyMemory: could not parse %s - starting fresh", self._path)
        return {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            _log.warning("StrategyMemory: could not write to %s", self._path)


# Module-level singleton - lazy-loaded
_memory: StrategyMemory | None = None


def load_strategy_memory(path: Path | None = None) -> StrategyMemory:
    """Return the shared StrategyMemory instance (singleton per process)."""
    global _memory  # noqa: PLW0603
    if _memory is None or path is not None:
        _memory = StrategyMemory(path=path)
    return _memory

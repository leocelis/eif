"""EIF cumulative cost ledger - persists total modeled cost-protected across HALTs.

Answers: "how much modeled decision cost has EIF blocked in this session
history?" The figures are modeled estimates (see LEGAL.md), not measured savings.

Storage: JSON file at ~/.eif/cost_ledger.json.
Keyed by session_id (local) or a caller-supplied key for shared-server deployments.

Schema per record:
  {
    "<session_or_key_id>": {
      "total_expected": 31200.00,
      "halt_count":     7,
      "first_halt_at":  "2026-05-10T20:00:00+00:00",
      "last_halt_at":   "2026-05-10T21:15:00+00:00"
    }
  }

Design:
  - Thread-safe: file writes are serialised via a threading.Lock.
  - Cumulative: records accumulate across sessions and are never reset by
    this module. To start fresh, delete ~/.eif/cost_ledger.json.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

_DEFAULT_PATH = Path(os.environ.get("EIF_COST_LEDGER_PATH", Path.home() / ".eif" / "cost_ledger.json"))


class CostLedger:
    """Cumulative cost-protected ledger per session or API key.

    Usage:
        ledger = CostLedger()
        ledger.record_halt(key="session-abc", expected_cost=7875.0)
        summary = ledger.get_summary("session-abc")
        # {"total_expected": 7875.0, "halt_count": 1, ...}
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._lock = threading.Lock()
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp, self._path)

    def record_halt(self, key: str, expected_cost: float) -> dict:
        """Record one HALT event for the given key. Returns updated summary."""
        now = datetime.now(UTC).isoformat()
        with self._lock:
            record = self._data.get(key)
            if record is None:
                record = {
                    "total_expected": 0.0,
                    "halt_count": 0,
                    "first_halt_at": now,
                    "last_halt_at": now,
                }
            record["total_expected"] = round(record["total_expected"] + expected_cost, 2)
            record["halt_count"] += 1
            record["last_halt_at"] = now
            self._data[key] = record
            self._save()
            return dict(record)

    def get_summary(self, key: str) -> dict:
        """Return cumulative summary for the given key, or zeros if no history."""
        with self._lock:
            record = self._data.get(key)
            if record is None:
                return {
                    "total_expected": 0.0,
                    "halt_count": 0,
                    "first_halt_at": None,
                    "last_halt_at": None,
                }
            return dict(record)


# Module-level singleton for local use
_ledger: CostLedger | None = None


def get_ledger() -> CostLedger:
    global _ledger
    if _ledger is None:
        _ledger = CostLedger()
    return _ledger

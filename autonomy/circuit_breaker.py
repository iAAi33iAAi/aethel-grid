#!/usr/bin/env python3
"""
CAIOS persistent circuit breaker.

Prevents autonomous repetition of the same failed intent after a bounded
failure budget. Quarantine is keyed by observed state digest and action
fingerprint.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CircuitRecord:
    key: str
    state_digest: str
    failures: int
    last_outcome: str
    quarantined: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "state_digest": self.state_digest,
            "failures": self.failures,
            "last_outcome": self.last_outcome,
            "quarantined": self.quarantined,
        }


class CircuitBreaker:
    def __init__(self, path: Path, failure_budget: int = 3) -> None:
        self.path = path
        self.failure_budget = max(1, int(failure_budget))

    def _read(self) -> dict[str, CircuitRecord]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}

        rows: dict[str, CircuitRecord] = {}
        for key, item in raw.items():
            try:
                rows[str(key)] = CircuitRecord(
                    key=str(item["key"]),
                    state_digest=str(item["state_digest"]),
                    failures=int(item["failures"]),
                    last_outcome=str(item["last_outcome"]),
                    quarantined=bool(item["quarantined"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
        return rows

    def _write(self, rows: dict[str, CircuitRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            key: row.as_dict()
            for key, row in sorted(rows.items())
        }
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def make_key(state_digest: str, action_fingerprint: str) -> str:
        payload = f"{state_digest}:{action_fingerprint}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def allowed(
        self,
        state_digest: str,
        action_fingerprint: str,
    ) -> tuple[bool, str]:
        key = self.make_key(state_digest, action_fingerprint)
        row = self._read().get(key)
        if row is None:
            return True, "not-recorded"
        if row.state_digest != state_digest:
            return True, "state-changed"
        if row.quarantined:
            return False, "quarantined"
        return True, "within-budget"

    def record(
        self,
        state_digest: str,
        action_fingerprint: str,
        outcome: str,
    ) -> CircuitRecord:
        key = self.make_key(state_digest, action_fingerprint)
        rows = self._read()
        previous = rows.get(key)
        failures = previous.failures if previous else 0

        if outcome in {"FAIL", "BLOCKED"}:
            failures += 1
        else:
            failures = 0

        row = CircuitRecord(
            key=key,
            state_digest=state_digest,
            failures=failures,
            last_outcome=str(outcome),
            quarantined=failures >= self.failure_budget,
        )
        rows[key] = row
        self._write(rows)
        return row

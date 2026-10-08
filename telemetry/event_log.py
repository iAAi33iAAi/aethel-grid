#!/usr/bin/env python3
"""
CAIOS JSONL telemetry sink.

Telemetry is intentionally non-authoritative. It is never consulted by the
constitutional gate and never modifies proof decisions.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
from pathlib import Path

from telemetry.caios_events import TelemetryEvent


class TelemetryLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, event: TelemetryEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = json.dumps(event.as_dict(), sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(row + "\n")

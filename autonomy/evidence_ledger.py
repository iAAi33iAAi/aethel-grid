#!/usr/bin/env python3
"""
CAIOS append-only evidence ledger.

Certificates prove decisions. The evidence ledger preserves the ordered stream
of evidence that was observed while those decisions were made.

Each entry commits to the previous entry, cycle, evidence payload, and source.
The ledger verifier is intentionally independent of the certificate verifier.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    import hashlib
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class EvidenceEvent:
    sequence: int
    cycle: int
    kind: str
    status: str
    source: str
    evidence_digest: str
    details_digest: str
    previous_event_digest: str | None

    @property
    def event_digest(self) -> str:
        material = asdict(self)
        return digest(material)

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "event_digest": self.event_digest,
        }


class EvidenceLedger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def append(
        self,
        cycle: int,
        evidence: Iterable[Any],
    ) -> list[EvidenceEvent]:
        rows = self._read()
        sequence = len(rows) + 1
        previous = rows[-1].get("event_digest") if rows else None
        events = []

        for item in evidence:
            payload = item.as_dict() if hasattr(item, "as_dict") else dict(item)
            event = EvidenceEvent(
                sequence=sequence,
                cycle=int(cycle),
                kind=str(payload.get("kind", "unknown")),
                status=str(payload.get("status", "UNKNOWN")),
                source=str(payload.get("source", "unknown")),
                evidence_digest=str(payload.get("digest", digest(payload))),
                details_digest=digest(payload.get("details", {})),
                previous_event_digest=previous,
            )
            events.append(event)
            sequence += 1
            previous = event.event_digest

        if events:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event.as_dict(), sort_keys=True) + "\n")
        return events


def verify(path: Path) -> tuple[bool, list[str]]:
    errors = []
    previous = None
    expected_sequence = 1

    if not path.is_file():
        return False, ["ledger-missing"]

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            event = EvidenceEvent(
                sequence=int(row["sequence"]),
                cycle=int(row["cycle"]),
                kind=str(row["kind"]),
                status=str(row["status"]),
                source=str(row["source"]),
                evidence_digest=str(row["evidence_digest"]),
                details_digest=str(row["details_digest"]),
                previous_event_digest=row.get("previous_event_digest"),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"line {line_number}: malformed:{type(exc).__name__}")
            continue

        if event.sequence != expected_sequence:
            errors.append(f"line {line_number}: sequence-mismatch")
        if event.previous_event_digest != previous:
            errors.append(f"line {line_number}: previous-event-digest-mismatch")
        if row.get("event_digest") != event.event_digest:
            errors.append(f"line {line_number}: event-digest-mismatch")

        previous = event.event_digest
        expected_sequence += 1

    return not errors, errors

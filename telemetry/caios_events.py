#!/usr/bin/env python3
"""
CAIOS OpenTelemetry-compatible event schema.

SDK-free event factory using stable semantic attribute names. Exporters may
later forward these events to an OpenTelemetry collector without changing the
control plane.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any


SERVICE_NAME = "caios"
SCHEMA_URL = "https://github.com/iAAi33iAAi/aethel-grid/telemetry/caios/v1"


def digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class TelemetryEvent:
    event_name: str
    trace_id: str
    span_id: str
    timestamp_ns: int
    attributes: dict[str, Any]
    body: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_url": SCHEMA_URL,
            "event_name": self.event_name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "timestamp_unix_nano": self.timestamp_ns,
            "attributes": self.attributes,
            "body": self.body,
            "event_digest": digest({
                "event_name": self.event_name,
                "trace_id": self.trace_id,
                "span_id": self.span_id,
                "timestamp_unix_nano": self.timestamp_ns,
                "attributes": self.attributes,
                "body": self.body,
            }),
        }


def new_event(
    event_name: str,
    *,
    trace_id: str | None = None,
    span_id: str | None = None,
    attributes: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> TelemetryEvent:
    attrs = {
        "service.name": SERVICE_NAME,
        "service.version": "1",
        "telemetry.sdk.name": "caios-native",
        **(attributes or {}),
    }
    return TelemetryEvent(
        event_name=event_name,
        trace_id=trace_id or uuid.uuid4().hex,
        span_id=span_id or uuid.uuid4().hex[:16],
        timestamp_ns=time.time_ns(),
        attributes=attrs,
        body=body or {},
    )


EVENT_NAMES = (
    "caios.cycle.started",
    "caios.agent.admitted",
    "caios.route.selected",
    "caios.action.simulated",
    "caios.action.executed",
    "caios.evidence.observed",
    "caios.proof.sealed",
    "caios.promotion.evaluated",
    "caios.directive.generated",
)

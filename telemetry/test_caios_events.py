from pathlib import Path
import json

from telemetry.caios_events import new_event
from telemetry.event_log import TelemetryLog


def test_telemetry_event_uses_standard_service_attributes(tmp_path: Path):
    event = new_event(
        "caios.cycle.started",
        trace_id="trace",
        span_id="span",
        attributes={"deployment.environment.name":"ci"},
        body={"cycle":1},
    )
    row = event.as_dict()
    assert row["attributes"]["service.name"] == "caios"
    assert row["trace_id"] == "trace"
    assert row["event_digest"]


def test_telemetry_log_is_append_only_jsonl(tmp_path: Path):
    path = tmp_path / "telemetry.jsonl"
    log = TelemetryLog(path)
    log.write(new_event("caios.cycle.started", trace_id="t", span_id="s", body={"cycle":1}))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event_name"] == "caios.cycle.started"

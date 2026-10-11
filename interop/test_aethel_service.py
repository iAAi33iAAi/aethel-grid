import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from interop.aethel_service import (
    Handler,
    MAX_REQUEST_BYTES,
    PROTOCOL,
    canonical_json,
    evaluate,
    strict_json_loads,
)


def test_state_rebuild_is_deterministic():
    events = [
        {"id": "b", "parents": ["a"], "state": {"x": 2}},
        {"id": "a", "parents": [], "state": {"x": 1, "y": 3}},
    ]
    result = evaluate("r1", "state-rebuild", {"events": events})
    assert result["status"] == "PASS"
    assert result["result"]["state"] == {"x": 2, "y": 3}
    assert result["result"]["ordered_event_ids"] == ["a", "b"]


def test_cycle_fails_closed():
    events = [
        {"id": "a", "parents": ["b"], "state": {}},
        {"id": "b", "parents": ["a"], "state": {}},
    ]
    result = evaluate("r2", "state-rebuild", {"events": events})
    assert result["status"] == "FAIL"


def test_canonical_conformance_remains_blocked():
    result = evaluate("r3", "conformance-status", {})
    assert result["status"] == "BLOCKED"
    assert result["decision"] == "HOLD"


def test_missing_parent_fails_closed():
    result = evaluate(
        "r4",
        "state-rebuild",
        {"events": [{"id": "b", "parents": ["missing"], "state": {}}]},
    )
    assert result["status"] == "FAIL"


def test_health_is_healthy_while_conformance_is_blocked():
    result = evaluate("health", "conformance-status", {})
    assert result["status"] == "BLOCKED"


@pytest.mark.parametrize(
    "raw",
    [
        '{"a":1,"a":2}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
    ],
)
def test_strict_json_rejects_duplicate_keys_and_nonstandard_numbers(raw):
    with pytest.raises(ValueError):
        strict_json_loads(raw)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_encoding_rejects_nonfinite_numbers(value):
    with pytest.raises(ValueError):
        canonical_json({"metric": value})


def test_event_hash_fails_closed_on_nonfinite_metrics():
    result = evaluate("r5", "event-hash", {"event": {"id": "evt", "metric": float("nan")}})
    assert result["status"] == "FAIL"
    assert "non-finite" in result["reasons"][0]


def test_duplicate_event_ids_fail_closed():
    events = [
        {"id": "same", "parents": [], "state": {"x": 1}},
        {"id": "same", "parents": [], "state": {"x": 2}},
    ]
    result = evaluate("r6", "state-rebuild", {"events": events})
    assert result["status"] == "FAIL"
    assert "duplicate event id" in result["reasons"][0]


def test_malformed_event_envelopes_fail_closed():
    cases = [
        [{"id": "", "parents": [], "state": {}}],
        [{"id": "a", "parents": "b", "state": {}}],
        [{"id": "a", "parents": [], "state": []}],
        ["not-an-event"],
    ]
    for events in cases:
        result = evaluate("r7", "state-rebuild", {"events": events})
        assert result["status"] == "FAIL"


def test_direct_evaluate_rejects_non_object_payload():
    result = evaluate("r8", "state-rebuild", [])
    assert result["status"] == "FAIL"


@pytest.fixture
def http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _post(server, body: bytes, *, declared_length: int | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    headers = {"Content-Type": "application/json"}
    if declared_length is not None:
        headers["Content-Length"] = str(declared_length)
        # Send a deliberately shorter body to verify size is rejected before reading.
        connection.putrequest("POST", "/aethel/evaluate")
        for name, value in headers.items():
            connection.putheader(name, value)
        connection.endheaders()
        connection.send(body)
    else:
        connection.request("POST", "/aethel/evaluate", body=body, headers=headers)
    response = connection.getresponse()
    result = (response.status, response.read())
    connection.close()
    return result


def test_http_rejects_duplicate_keys_and_nonstandard_numbers(http_server):
    cases = [
        b'{"protocol":"aethel-interop/1","protocol":"wrong","request_id":"r","operation":"event-hash","payload":{"event":{"id":"x"}}}',
        b'{"protocol":"aethel-interop/1","request_id":"r","operation":"event-hash","payload":{"event":{"metric":NaN}}}',
    ]
    for body in cases:
        status, raw = _post(http_server, body)
        assert status == 400
        assert b"error" in raw


def test_http_rejects_non_object_envelope_or_payload(http_server):
    for body in (
        b'[]',
        b'{"protocol":"aethel-interop/1","request_id":"r","operation":"event-hash","payload":[]}',
    ):
        status, _ = _post(http_server, body)
        assert status == 400


def test_http_rejects_oversized_declared_body_before_reading(http_server):
    status, raw = _post(http_server, b"x", declared_length=MAX_REQUEST_BYTES + 1)
    assert status == 413
    assert b"too large" in raw


def test_http_evaluate_uses_strict_request_schema(http_server):
    body = json.dumps({
        "protocol": PROTOCOL,
        "request_id": "r9",
        "operation": "conformance-status",
        "payload": {},
    }).encode("utf-8")
    status, raw = _post(http_server, body)
    assert status == 200
    result = json.loads(raw)
    assert result["status"] == "BLOCKED"
    assert result["decision"] == "HOLD"

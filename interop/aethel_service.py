"""AETHEL Grid reference-bootstrap service.

This is an executable reconstruction of the event-sourcing equation described
by the repository: STATE(G) = fold(topo_order(closure(G))).

It is deliberately named a bootstrap implementation. It does not claim to
replace the unresolved SPEC-004 canonical validator or supplied golden vectors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


PROTOCOL = "aethel-interop/1"
SERVICE = "aethel-grid"
VERSION = "bootstrap-0.1.0"
MAX_REQUEST_BYTES = 2_000_000
MAX_EVENTS_PER_REQUEST = 5_000
MAX_REQUEST_ID_CHARS = 128


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is forbidden: {value}")


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def strict_json_loads(raw: str) -> Any:
    """Reject duplicate keys and non-standard NaN/Infinity extensions."""
    return json.loads(
        raw,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_object_keys,
    )


def _reject_non_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers are not permitted in protocol data")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            _reject_non_finite(item)
    elif isinstance(value, list):
        for item in value:
            _reject_non_finite(item)


def canonical_json(value: Any) -> bytes:
    """Deterministic UTF-8 JSON; non-finite numbers and non-string keys fail closed."""
    _reject_non_finite(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _validate_events(events: Any) -> list[dict[str, Any]]:
    """Validate the event envelope before reconstructing any state."""
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    if len(events) > MAX_EVENTS_PER_REQUEST:
        raise ValueError(f"events exceeds limit of {MAX_EVENTS_PER_REQUEST}")

    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"event at index {index} must be an object")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError(f"event at index {index} must have a non-empty string id")
        if event_id in seen:
            raise ValueError(f"duplicate event id: {event_id}")
        seen.add(event_id)

        parents = event.get("parents", [])
        if not isinstance(parents, list) or any(
            not isinstance(parent, str) or not parent.strip() for parent in parents
        ):
            raise ValueError(f"event {event_id} parents must be a list of non-empty strings")
        if len(set(parents)) != len(parents):
            raise ValueError(f"event {event_id} contains duplicate parents")

        state = event.get("state", {})
        if not isinstance(state, dict):
            raise ValueError(f"event {event_id} state must be an object")
        _reject_non_finite(event)
        validated.append(event)
    return validated


def event_digest(event: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(event)).hexdigest()


def closure(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = _validate_events(events)
    by_id = {e["id"]: e for e in events}
    needed: set[str] = set()
    frontier = list(by_id)
    while frontier:
        current = frontier.pop()
        if current in needed:
            continue
        needed.add(current)
        for parent in by_id[current].get("parents", []):
            parent_id = str(parent)
            if parent_id not in by_id:
                raise ValueError(f"missing causal parent: {parent_id}")
            if parent_id not in needed:
                frontier.append(parent_id)
    return [by_id[event_id] for event_id in needed]


def topo_order(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = closure(events)
    by_id = {e["id"]: e for e in selected}
    indegree = {event_id: 0 for event_id in by_id}
    children: dict[str, list[str]] = {event_id: [] for event_id in by_id}
    for event_id, event in by_id.items():
        for parent in event.get("parents", []):
            parent_id = str(parent)
            if parent_id in by_id:
                indegree[event_id] += 1
                children[parent_id].append(event_id)

    ready = sorted([event_id for event_id, degree in indegree.items() if degree == 0])
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready.sort()

    if len(ordered) != len(by_id):
        raise ValueError("causal graph contains a cycle")
    return [by_id[event_id] for event_id in ordered]


def fold(events: list[dict[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for event in topo_order(events):
        patch = event.get("state", {})
        if not isinstance(patch, dict):
            raise ValueError("event.state must be an object")
        state.update(patch)
    return state


def evaluate(request_id: str, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > MAX_REQUEST_ID_CHARS:
            raise ValueError(f"request_id must be a non-empty string of at most {MAX_REQUEST_ID_CHARS} characters")
        if not isinstance(operation, str) or not operation:
            raise ValueError("operation must be a non-empty string")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        _reject_non_finite(payload)

        if operation == "state-rebuild":
            events = _validate_events(payload.get("events", []))
            ordered = topo_order(events)
            state = fold(events)
            history_digest = hashlib.sha256(
                canonical_json([event_digest(event) for event in ordered])
            ).hexdigest()
            return {
                "protocol": PROTOCOL,
                "service": SERVICE,
                "version": VERSION,
                "request_id": request_id,
                "status": "PASS",
                "decision": "REBUILT",
                "reasons": [],
                "result": {
                    "state": state,
                    "ordered_event_ids": [str(e["id"]) for e in ordered],
                    "history_digest": history_digest,
                },
                "evidence": {
                    "implementation": VERSION,
                    "semantic_equation": "STATE(G)=fold(topo_order(closure(G)))",
                },
            }

        if operation == "event-hash":
            event = payload.get("event")
            if not isinstance(event, dict):
                raise ValueError("event must be an object")
            _reject_non_finite(event)
            digest = event_digest(event)
            return {
                "protocol": PROTOCOL,
                "service": SERVICE,
                "version": VERSION,
                "request_id": request_id,
                "status": "PASS",
                "decision": "HASHED",
                "reasons": [],
                "result": {"sha256": digest},
                "evidence": {"canonical_encoding": "json(sort_keys,separators,no-ascii-escaping)"},
            }

        if operation == "conformance-status":
            return {
                "protocol": PROTOCOL,
                "service": SERVICE,
                "version": VERSION,
                "request_id": request_id,
                "status": "BLOCKED",
                "decision": "HOLD",
                "reasons": [
                    "Canonical SPEC-004 execution is not established by the current repository tree.",
                    "Do not substitute the bootstrap event engine for authoritative golden-vector conformance.",
                ],
                "result": {"canonical_validator": "not-established"},
                "evidence": {"implementation": VERSION},
            }

        raise ValueError(f"unsupported operation: {operation}")
    except (TypeError, ValueError, KeyError) as exc:
        return {
            "protocol": PROTOCOL,
            "service": SERVICE,
            "version": VERSION,
            "request_id": request_id,
            "status": "FAIL",
            "decision": "INVALID_INPUT",
            "reasons": [str(exc)],
            "result": {},
            "evidence": {},
        }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body, sort_keys=True, allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/aethel/health":
            self._send(200, {
                "protocol": PROTOCOL,
                "service": SERVICE,
                "version": VERSION,
                "request_id": "health",
                "status": "PASS",
                "decision": "HEALTHY",
                "reasons": [],
                "result": {},
                "evidence": {"canonical_conformance": "blocked"},
            })
            return
        if self.path == "/aethel/capabilities":
            self._send(
                200,
                {
                    "protocol": PROTOCOL,
                    "service": SERVICE,
                    "version": VERSION,
                    "operations": ["state-rebuild", "event-hash", "conformance-status"],
                    "canonical_conformance": "blocked",
                },
            )
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/aethel/evaluate":
            self._send(404, {"error": "not found"})
            return
        try:
            raw_size = self.headers.get("Content-Length", "")
            if not raw_size.isascii() or not raw_size.isdigit():
                self._send(400, {"error": "valid Content-Length is required"})
                return
            size = int(raw_size)
            if size <= 0:
                self._send(400, {"error": "request body is required"})
                return
            if size > MAX_REQUEST_BYTES:
                self._send(413, {"error": "request body too large"})
                return

            raw_body = self.rfile.read(size)
            if len(raw_body) != size:
                self._send(400, {"error": "request body was shorter than Content-Length"})
                return
            body = strict_json_loads(raw_body.decode("utf-8"))
            if not isinstance(body, dict):
                self._send(400, {"error": "request body must be a JSON object"})
                return
            if body.get("protocol") != PROTOCOL:
                self._send(400, {"error": "unsupported protocol"})
                return

            request_id = body.get("request_id")
            if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > MAX_REQUEST_ID_CHARS:
                self._send(400, {"error": "request_id must be a non-empty string of at most 128 characters"})
                return
            operation = body.get("operation")
            if not isinstance(operation, str) or not operation:
                self._send(400, {"error": "operation must be a non-empty string"})
                return
            payload = body.get("payload", {})
            if not isinstance(payload, dict):
                self._send(400, {"error": "payload must be an object"})
                return

            self._send(200, evaluate(request_id, operation, payload))
        except (TypeError, ValueError, KeyError, UnicodeDecodeError) as exc:
            self._send(400, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8103)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


PROTOCOL = "aethel-interop/1"
SERVICE = "aethel-grid"
VERSION = "bootstrap-0.1.0"


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def event_digest(event: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(event)).hexdigest()


def closure(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(e["id"]): e for e in events}
    needed: set[str] = set()
    frontier = list(by_id)
    while frontier:
        current = frontier.pop()
        if current in needed:
            continue
        needed.add(current)
        for parent in by_id[current].get("parents", []):
            parent_id = str(parent)
            if parent_id in by_id and parent_id not in needed:
                frontier.append(parent_id)
    return [by_id[event_id] for event_id in needed]


def topo_order(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = closure(events)
    by_id = {str(e["id"]): e for e in selected}
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
        if operation == "state-rebuild":
            events = payload.get("events", [])
            if not isinstance(events, list):
                raise ValueError("events must be a list")
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
        raw = json.dumps(body, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/aethel/health":
            self._send(200, evaluate("health", "conformance-status", {}))
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
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size).decode("utf-8"))
            if body.get("protocol") != PROTOCOL:
                self._send(400, {"error": "unsupported protocol"})
                return
            self._send(
                200,
                evaluate(
                    str(body["request_id"]),
                    str(body.get("operation", "")),
                    dict(body.get("payload", {})),
                ),
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
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

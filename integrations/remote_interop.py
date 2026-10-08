#!/usr/bin/env python3
"""
CAIOS remote AETHEL interop evidence adapter.

Consumes the repository family's aethel-interop/1 response contract as
evidence only. A remote response can never become an execution authorization.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


EXPECTED_PROTOCOL = "aethel-interop/1"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class InteropEvidence:
    protocol: str
    service: str
    version: str
    request_id: str
    status: str
    decision: str
    reasons: tuple[str, ...]
    result: dict[str, Any]
    evidence: dict[str, Any]

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "InteropEvidence":
        if not isinstance(value, dict):
            raise ValueError("interop response must be an object")
        if value.get("protocol") != EXPECTED_PROTOCOL:
            raise ValueError("interop protocol mismatch")
        required = ("service", "version", "request_id", "status", "decision")
        missing = [key for key in required if not isinstance(value.get(key), str)]
        if missing:
            raise ValueError("missing required string fields: " + ",".join(missing))
        reasons = value.get("reasons", [])
        result = value.get("result", {})
        evidence = value.get("evidence", {})
        if not isinstance(reasons, list) or not isinstance(result, dict) or not isinstance(evidence, dict):
            raise ValueError("interop response fields have invalid types")
        return cls(
            protocol=EXPECTED_PROTOCOL,
            service=value["service"],
            version=value["version"],
            request_id=value["request_id"],
            status=value["status"],
            decision=value["decision"],
            reasons=tuple(str(item) for item in reasons),
            result=result,
            evidence=evidence,
        )

    @property
    def response_digest(self) -> str:
        return digest({
            "protocol": self.protocol,
            "service": self.service,
            "version": self.version,
            "request_id": self.request_id,
            "status": self.status,
            "decision": self.decision,
            "reasons": list(self.reasons),
            "result": self.result,
            "evidence": self.evidence,
        })


def validate_endpoint(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("interop endpoint must be an absolute HTTP(S) URL")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("non-local interop endpoints must use HTTPS")


class RemoteInteropClient:
    def __init__(self, url: str, bearer_token: str | None = None, timeout_seconds: int = 20) -> None:
        validate_endpoint(url)
        self.url = url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds

    def evaluate(self, request_id: str, operation: str, payload: dict[str, Any]) -> InteropEvidence:
        body = {
            "request_id": request_id,
            "operation": operation,
            "payload": payload,
        }
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        request = urllib.request.Request(
            self.url + "/evaluate",
            data=json.dumps(body, sort_keys=True).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("interop response exceeds 1 MiB safety limit")
        return InteropEvidence.from_json(json.loads(raw.decode("utf-8")))

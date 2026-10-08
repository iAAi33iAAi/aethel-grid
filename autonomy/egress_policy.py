#!/usr/bin/env python3
"""
CAIOS data egress policy.

Classifies outbound model context before network transmission. The default
policy is conservative: credential-like content is BLOCKED, large context is
BLOCKED, and only explicitly permitted outbound categories are allowed.

This does not inspect or transmit data itself.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[^\s]{8,}"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[^\s]+"),
    re.compile(r"(?i)aws_secret_access_key\s*=\s*[^\s]+"),
)


@dataclass(frozen=True)
class EgressDecision:
    status: str
    reasons: tuple[str, ...]
    bytes_out: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "bytes_out": self.bytes_out,
            "digest": self.digest,
        }


class EgressPolicy:
    def __init__(
        self,
        max_context_bytes: int = 2_000_000,
        allow_source_context: bool = False,
    ) -> None:
        self.max_context_bytes = int(max_context_bytes)
        self.allow_source_context = bool(allow_source_context)

    @staticmethod
    def _digest(payload: str) -> str:
        import hashlib
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def inspect(self, payload: str, *, source_context: bool = False) -> EgressDecision:
        raw = str(payload)
        reasons: list[str] = []
        size = len(raw.encode("utf-8"))

        if size > self.max_context_bytes:
            reasons.append("payload-exceeds-max-context-bytes")
        if source_context and not self.allow_source_context:
            reasons.append("source-context-egress-disabled-by-default")

        for pattern in _SECRET_PATTERNS:
            if pattern.search(raw):
                reasons.append("credential-like-material-detected")
                break

        return EgressDecision(
            status="BLOCKED" if reasons else "ALLOW",
            reasons=tuple(sorted(set(reasons))),
            bytes_out=size,
            digest=self._digest(raw),
        )


def scan_context(
    context: Any,
    policy: EgressPolicy,
    *,
    source_context: bool = True,
) -> EgressDecision:
    if context is None:
        return policy.inspect("", source_context=source_context)

    if isinstance(context, str):
        return policy.inspect(context, source_context=source_context)

    try:
        payload = json.dumps(context, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return EgressDecision(
            status="BLOCKED",
            reasons=("context-not-json-serializable",),
            bytes_out=0,
            digest="",
        )
    return policy.inspect(payload, source_context=source_context)

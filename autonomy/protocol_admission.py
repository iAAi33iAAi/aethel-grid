#!/usr/bin/env python3
"""
CAIOS protocol admission and capability negotiation.

A protocol can transport information without possessing policy authority.
Draft versions require explicit operator opt-in. Capabilities are treated as
features, never as permission.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProtocolProfile:
    protocol_id: str
    version: str
    status: str
    role: str
    license: str
    source_url: str
    draft: bool
    conformance_tool: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "version": self.version,
            "status": self.status,
            "role": self.role,
            "license": self.license,
            "source_url": self.source_url,
            "draft": self.draft,
            "conformance_tool": self.conformance_tool,
        }


class ProtocolRegistry:
    def __init__(self, repo_root: Path, path: str = "autonomy/protocol_registry.json") -> None:
        raw = json.loads((repo_root / path).read_text(encoding="utf-8"))
        self.policy = dict(raw.get("policy", {}))
        self.protocols = {
            item["id"]: ProtocolProfile(
                protocol_id=str(item["id"]),
                version=str(item["latest_known_revision"]),
                status=str(item["status"]),
                role=str(item["transport_role"]),
                license=str(item["license"]),
                source_url=str(item["source_url"]),
                draft=bool(item.get("draft", False)),
                conformance_tool=item.get("conformance_tool"),
            )
            for item in raw.get("protocols", [])
        }

    def get(self, protocol_id: str) -> ProtocolProfile | None:
        return self.protocols.get(protocol_id)

    def admit(self, protocol_id: str, version: str, *, allow_draft: bool = False) -> tuple[bool, list[str]]:
        profile = self.get(protocol_id)
        if profile is None:
            return False, ["protocol-not-registered"]

        reasons = []
        if profile.draft and self.policy.get("draft_protocol_requires_opt_in", True) and not allow_draft:
            reasons.append("draft-protocol-opt-in-required")

        if profile.version != str(version):
            reasons.append("protocol-version-not-currently-admitted")

        return not reasons, reasons


def normalize_capabilities(
    protocol_id: str,
    version: str,
    capabilities: dict[str, Any] | None,
) -> dict[str, Any]:
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    return {
        "protocol": protocol_id,
        "version": str(version),
        "capabilities": capabilities,
        "capability_count": len(capabilities),
    }

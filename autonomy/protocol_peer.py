#!/usr/bin/env python3
"""
CAIOS protocol-neutral peer descriptor.

Normalizes ACP initialization responses and A2A Agent Cards without depending
on either SDK. This is an adapter layer, not an authority layer.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autonomy.protocol_admission import ProtocolRegistry, normalize_capabilities


@dataclass(frozen=True)
class PeerDescriptor:
    peer_id: str
    protocol: str
    protocol_version: str
    name: str
    version: str
    capabilities: dict[str, Any]
    transport: dict[str, Any]
    security: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "protocol": self.protocol,
            "protocol_version": self.protocol_version,
            "name": self.name,
            "version": self.version,
            "capabilities": self.capabilities,
            "transport": self.transport,
            "security": self.security,
        }


def from_acp_initialize(response: dict[str, Any]) -> PeerDescriptor:
    result = response.get("result", response)
    if not isinstance(result, dict):
        raise ValueError("ACP initialization result must be an object")

    protocol_version = str(result.get("protocolVersion", ""))
    info = result.get("agentInfo") or result.get("info") or {}
    if not protocol_version or not isinstance(info, dict):
        raise ValueError("ACP peer missing protocolVersion or info")

    name = str(info.get("name", "unknown"))
    version = str(info.get("version", "unknown"))
    capabilities = result.get("capabilities") if isinstance(result.get("capabilities"), dict) else {}
    peer_id = f"acp:{name}:{version}"

    return PeerDescriptor(
        peer_id=peer_id,
        protocol="acp",
        protocol_version=protocol_version,
        name=name,
        version=version,
        capabilities=normalize_capabilities("acp", protocol_version, capabilities),
        transport={"kind": "acp"},
        security={"authentication": result.get("authMethods", [])},
    )


def from_a2a_card(card: dict[str, Any]) -> PeerDescriptor:
    if not isinstance(card, dict):
        raise ValueError("A2A Agent Card must be an object")

    name = str(card.get("name", "unknown"))
    version = str(card.get("version", "unknown"))
    protocol_version = str(
        card.get("protocolVersion")
        or card.get("supportedInterfaces", [{}])[0].get("protocolBindingVersion", "1.0")
    )
    if not protocol_version:
        raise ValueError("A2A peer missing protocol version")

    peer_id = f"a2a:{name}:{version}"
    capabilities = card.get("capabilities") if isinstance(card.get("capabilities"), dict) else {}

    return PeerDescriptor(
        peer_id=peer_id,
        protocol="a2a",
        protocol_version=protocol_version,
        name=name,
        version=version,
        capabilities=normalize_capabilities("a2a", protocol_version, capabilities),
        transport={"interfaces": card.get("supportedInterfaces", [])},
        security={"securitySchemes": card.get("securitySchemes", {})},
    )


def admit_peer(repo_root, descriptor: PeerDescriptor) -> tuple[bool, list[str]]:
    registry = ProtocolRegistry(repo_root)
    ok, reasons = registry.admit(
        descriptor.protocol,
        descriptor.protocol_version,
        allow_draft=False,
    )
    return ok, reasons

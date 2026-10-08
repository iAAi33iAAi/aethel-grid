#!/usr/bin/env python3
"""
CAIOS cross-protocol route selector.

Selects a transport path based on work intent, peer capabilities, admitted
protocol revisions, risk, and authority boundary.

The selector does not execute transport operations. It produces a route plan.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from autonomy.protocol_admission import ProtocolRegistry
from autonomy.protocol_peer import PeerDescriptor


@dataclass(frozen=True)
class RouteDecision:
    protocol: str | None
    version: str | None
    purpose: str
    score: float
    reasons: tuple[str, ...]
    status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "version": self.version,
            "purpose": self.purpose,
            "score": self.score,
            "reasons": list(self.reasons),
            "status": self.status,
        }


def select_route(
    repo_root: Path,
    peers: Iterable[PeerDescriptor],
    *,
    purpose: str,
    required_capabilities: Iterable[str] = (),
    risk: float = 0.0,
) -> RouteDecision:
    registry = ProtocolRegistry(repo_root)
    required_capabilities = set(required_capabilities)

    preference = {
        "coding": {"acp": 1.0, "a2a": 0.45, "mcp": 0.20},
        "agent-to-agent": {"a2a": 1.0, "acp": 0.55, "mcp": 0.10},
        "tool-access": {"mcp": 1.0, "a2a": 0.25, "acp": 0.20},
        "evidence": {"aethel-interop": 1.0, "mcp": 0.25, "a2a": 0.20, "acp": 0.20},
    }.get(purpose, {})

    candidates: list[RouteDecision] = []
    for peer in peers:
        profile = registry.get(peer.protocol)
        if profile is None:
            continue
        admitted, _ = registry.admit(peer.protocol, peer.protocol_version, allow_draft=False)
        if not admitted:
            continue

        advertised = peer.capabilities.get("capabilities", {})
        capability_score = (
            sum(1 for key in required_capabilities if key in advertised)
            / len(required_capabilities)
            if required_capabilities else 1.0
        )
        base = preference.get(peer.protocol, 0.0)
        risk_penalty = 0.20 if risk >= 0.55 and peer.protocol == "mcp" else 0.0
        score = max(0.0, min(1.0, 0.65 * base + 0.25 * capability_score + 0.10 - risk_penalty))
        reasons = [
            f"purpose_fit={base:.2f}",
            f"capability_fit={capability_score:.2f}",
            f"risk_adjustment={risk_penalty:.2f}",
            "protocol_revision_admitted",
        ]
        candidates.append(
            RouteDecision(
                protocol=peer.protocol,
                version=peer.protocol_version,
                purpose=purpose,
                score=round(score, 6),
                reasons=tuple(reasons),
                status="ELIGIBLE",
            )
        )

    if not candidates:
        return RouteDecision(
            protocol=None,
            version=None,
            purpose=purpose,
            score=0.0,
            reasons=("no-admitted-peer-route",),
            status="BLOCKED",
        )

    candidates.sort(key=lambda item: (-item.score, item.protocol or "", item.version or ""))
    return candidates[0]

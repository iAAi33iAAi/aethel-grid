#!/usr/bin/env python3
"""
CAIOS agent proposal attestation.

An external proposal is admissible only when its declared agent identity and
protocol match the repository-owned registry. This prevents a model response
from presenting itself as an authority merely by choosing a different name.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autonomy.agent_router import AgentRegistry
from autonomy.model_admission import ModelRegistry


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ProposalAttestation:
    agent_id: str
    protocol: str
    model_id: str
    model_revision: str
    agent_version: str
    source_ref: str
    proposal_digest: str

    def as_dict(self) -> dict[str, str]:
        return {
            "agent_id": self.agent_id,
            "protocol": self.protocol,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "agent_version": self.agent_version,
            "source_ref": self.source_ref,
            "proposal_digest": self.proposal_digest,
        }

    @property
    def attestation_digest(self) -> str:
        return digest(self.as_dict())


def validate_proposal(
    repo_root: Path,
    proposal: dict[str, Any],
    proposal_digest: str,
) -> tuple[bool, list[str], ProposalAttestation | None]:
    agent_id = str(proposal.get("agent_id", ""))
    protocol = str(proposal.get("protocol", ""))
    model_id = str(proposal.get("model_id", ""))
    model_revision = str(proposal.get("model_revision", ""))
    agent_version = str(proposal.get("agent_version", ""))
    source_ref = str(proposal.get("source_ref", ""))

    reasons: list[str] = []
    try:
        registry = AgentRegistry(repo_root)
    except Exception as exc:
        return False, [f"agent-registry-unavailable:{type(exc).__name__}"], None

    profile = registry.agents.get(agent_id)
    if profile is None:
        return False, ["agent-id-not-registered"], None
    if profile.authority != "proposal":
        return False, ["agent-is-not-proposal-authority"], None
    if protocol not in profile.protocols:
        return False, ["protocol-not-advertised-by-agent"], None
    if profile.provenance_confidence < float(
        registry.policy.get("minimum_provenance_confidence", 0.90)
    ):
        return False, ["agent-provenance-confidence-below-floor"], None

    try:
        model_registry = ModelRegistry(repo_root)
    except Exception as exc:
        return False, [f"model-registry-unavailable:{type(exc).__name__}"], None

    model_admitted, model_reasons = model_registry.admit(
        model_id,
        model_revision=model_revision or None,
    )

    reasons.extend(model_reasons)

    for field_name, value in {
        "model_id": model_id,
        "model_revision": model_revision,
        "agent_version": agent_version,
        "source_ref": source_ref,
    }.items():
        if not value:
            reasons.append(f"{field_name}-missing")

    attestation = None
    if not reasons:
        attestation = ProposalAttestation(
            agent_id=agent_id,
            protocol=protocol,
            model_id=model_id,
            agent_version=agent_version,
            source_ref=source_ref,
            proposal_digest=proposal_digest,
        )
    return not reasons, reasons, attestation

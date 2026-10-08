#!/usr/bin/env python3
"""
CAIOS Proof-Carrying Work Contract verifier.

Cross-checks a PCWC against repository-owned registries. This verifier does
not trust transport metadata; it validates the contract against the local
policy surface.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autonomy.agent_router import AgentRegistry
from autonomy.model_admission import ModelRegistry
from autonomy.protocol_admission import ProtocolRegistry
from autonomy.proof_work_contract import ProofCarryingWorkContract
from integrations.tool_registry import ToolRegistry


def verify_contract(repo_root: Path, contract: ProofCarryingWorkContract) -> tuple[bool, list[str]]:
    reasons = []
    valid, contract_reasons = contract.validate()
    reasons.extend(contract_reasons)

    try:
        protocols = ProtocolRegistry(repo_root)
        protocol = protocols.get(contract.protocol)
        if protocol is None:
            reasons.append("protocol-not-registered")
        elif protocol.version != contract.protocol_version:
            reasons.append("protocol-version-not-current")
    except Exception as exc:
        reasons.append(f"protocol-registry-error:{type(exc).__name__}")

    if contract.agent_id:
        try:
            agents = AgentRegistry(repo_root)
            profile = agents.agents.get(contract.agent_id)
            if profile is None:
                reasons.append("agent-not-registered")
            elif contract.protocol not in profile.protocols:
                reasons.append("agent-does-not-advertise-protocol")
            elif profile.protocol_versions.get(contract.protocol) != contract.protocol_version:
                reasons.append("agent-protocol-version-mismatch")
        except Exception as exc:
            reasons.append(f"agent-registry-error:{type(exc).__name__}")

    if contract.model_id:
        try:
            models = ModelRegistry(repo_root)
            if models.get(contract.model_id) is None:
                reasons.append("model-not-registered")
        except Exception as exc:
            reasons.append(f"model-registry-error:{type(exc).__name__}")

    if contract.invariant_ids:
        registry_path = repo_root / "conformance" / "federated_invariant_registry.json"
        try:
            invariant_registry = json.loads(registry_path.read_text(encoding="utf-8"))
            known = {
                str(item["id"])
                for item in invariant_registry.get("invariants", [])
                if isinstance(item, dict) and "id" in item
            }
            for invariant_id in contract.invariant_ids:
                if invariant_id not in known:
                    reasons.append(f"invariant-not-registered:{invariant_id}")
        except (OSError, json.JSONDecodeError, TypeError):
            reasons.append("invariant-registry-unavailable")

    try:
        tools = ToolRegistry(repo_root)
        for tool_id in contract.tool_ids:
            if tools.get(tool_id) is None:
                reasons.append(f"tool-not-registered:{tool_id}")
    except Exception as exc:
        reasons.append(f"tool-registry-error:{type(exc).__name__}")

    if contract.decision == "PASS" and contract.risk >= 0.55 and not contract.simulation_digest:
        reasons.append("high-risk-passed-work-requires-simulation-digest")

    return not reasons, reasons

#!/usr/bin/env python3
"""
CAIOS Proof-Carrying Work Contract (PCWC).

A protocol-neutral transaction envelope for autonomous engineering work.
It binds intent, state, agent/model provenance, tool provenance, invariants,
simulation evidence, execution evidence, and rollback semantics.

PCWC is transport-independent: MCP, A2A, ACP, or AETHEL Interop can carry it.
None of those transports receives authority from the contract.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ProofCarryingWorkContract:
    work_id: str
    intent_fingerprint: str
    action_kind: str
    state_before: str
    state_after: str | None
    protocol: str
    protocol_version: str
    agent_id: str | None
    model_id: str | None
    model_revision: str | None
    agent_attestation: str | None
    tool_ids: tuple[str, ...] = ()
    invariant_ids: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    expected_gain: float = 0.0
    risk: float = 0.0
    reversibility: float = 1.0
    simulation_digest: str | None = None
    execution_digest: str | None = None
    rollback_plan: str = "restore prior state"
    decision: str = "PENDING"
    evidence_digests: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "caios-pcwc/v1",
            "work_id": self.work_id,
            "intent_fingerprint": self.intent_fingerprint,
            "action_kind": self.action_kind,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "protocol": self.protocol,
            "protocol_version": self.protocol_version,
            "agent_id": self.agent_id,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "agent_attestation": self.agent_attestation,
            "tool_ids": sorted(self.tool_ids),
            "invariant_ids": sorted(self.invariant_ids),
            "prerequisites": list(self.prerequisites),
            "expected_gain": self.expected_gain,
            "risk": self.risk,
            "reversibility": self.reversibility,
            "simulation_digest": self.simulation_digest,
            "execution_digest": self.execution_digest,
            "rollback_plan": self.rollback_plan,
            "decision": self.decision,
            "evidence_digests": list(self.evidence_digests),
        }

    @property
    def contract_digest(self) -> str:
        return digest(self.as_dict())

    def validate(self) -> tuple[bool, list[str]]:
        reasons = []
        for name, value in {
            "expected_gain": self.expected_gain,
            "risk": self.risk,
            "reversibility": self.reversibility,
        }.items():
            if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
                reasons.append(f"{name}-out-of-range")

        if not self.work_id:
            reasons.append("work-id-missing")
        if len(self.state_before) != 64:
            reasons.append("state-before-must-be-sha256")
        if self.state_after is not None and len(self.state_after) != 64:
            reasons.append("state-after-must-be-sha256")
        if not self.intent_fingerprint:
            reasons.append("intent-fingerprint-missing")
        if not self.action_kind:
            reasons.append("action-kind-missing")
        if not self.protocol or not self.protocol_version:
            reasons.append("protocol-identity-missing")
        if self.risk >= 0.55 and not self.invariant_ids:
            reasons.append("high-risk-work-requires-invariant-bindings")
        if self.action_kind in {"run_test", "run_security_scan", "apply_patch"} and not self.tool_ids:
            reasons.append("executable-work-requires-tool-bindings")
        if self.decision == "PASS" and not self.execution_digest:
            reasons.append("passed-work-requires-execution-evidence")
        if self.decision == "PASS" and self.state_after is None:
            reasons.append("passed-work-requires-post-state")

        return not reasons, reasons

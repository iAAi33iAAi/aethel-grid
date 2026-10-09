#!/usr/bin/env python3
"""
CAIOS agent arbitration and quorum engine.

The router does not execute agents. It creates a bounded assignment plan that
the CAIOS gate can consume. High-risk work requires independent agent families.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from autonomy.protocol_admission import ProtocolRegistry


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class AgentProfile:
    agent_id: str
    family: str
    protocols: frozenset[str]
    capabilities: frozenset[str]
    authority: str
    license: str
    sandbox: bool
    provenance_confidence: float
    protocol_versions: dict[str, str]
    software_version: str = ""
    source_ref: str = ""
    agent_kind: str = "external-agent"
    source_path: str = ""
    source_sha256: str = ""
    external_tool_execution: bool | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "family": self.family,
            "protocols": sorted(self.protocols),
            "capabilities": sorted(self.capabilities),
            "authority": self.authority,
            "license": self.license,
            "sandbox": self.sandbox,
            "provenance_confidence": self.provenance_confidence,
            "protocol_versions": dict(sorted(self.protocol_versions.items())),
            "software_version": self.software_version,
            "source_ref": self.source_ref,
            "agent_kind": self.agent_kind,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "external_tool_execution": self.external_tool_execution,
        }


@dataclass(frozen=True)
class AgentAssignment:
    agent_id: str
    score: float
    reasons: tuple[str, ...]
    profile_digest: str


@dataclass(frozen=True)
class QuorumPlan:
    assignments: tuple[AgentAssignment, ...]
    required_independent_families: int
    satisfied: bool
    plan_digest: str


class AgentRegistry:
    def __init__(self, repo_root: Path, path: str = "autonomy/agent_registry.json") -> None:
        self.repo_root = repo_root.resolve()
        raw = json.loads((self.repo_root / path).read_text(encoding="utf-8"))
        self.policy = dict(raw.get("selection_policy", {}))
        self.agents = {
            item["id"]: AgentProfile(
                agent_id=item["id"],
                family=item["family"],
                protocols=frozenset(item.get("protocols", [])),
                capabilities=frozenset(item.get("capabilities", [])),
                authority=item.get("authority", "proposal"),
                license=item.get("license", "UNKNOWN"),
                sandbox=bool(item.get("sandbox", False)),
                provenance_confidence=float(item.get("provenance_confidence", 0.0)),
                protocol_versions={
                    str(key): str(value)
                    for key, value in dict(item.get("protocol_versions", {})).items()
                },
                software_version=str(item.get("software_version", "")),
                source_ref=str(item.get("source_ref", "")),
                agent_kind=str(item.get("agent_kind", "external-agent")),
                source_path=str(item.get("source_path", "")),
                source_sha256=str(item.get("source_sha256", "")),
                external_tool_execution=(
                    bool(item["external_tool_execution"])
                    if "external_tool_execution" in item
                    else None
                ),
            )
            for item in raw.get("agents", [])
        }

    def _score(
        self,
        profile: AgentProfile,
        required_capabilities: Iterable[str],
        required_protocols: Iterable[str],
        risk: float,
        evidence_score: float,
        provenance_score: float,
    ) -> tuple[float, list[str]]:
        required_capabilities = frozenset(required_capabilities)
        required_protocols = frozenset(required_protocols)

        capability_match = (
            len(required_capabilities & profile.capabilities) / len(required_capabilities)
            if required_capabilities else 1.0
        )
        protocol_match = (
            len(required_protocols & profile.protocols) / len(required_protocols)
            if required_protocols else 1.0
        )
        sandbox_fit = 1.0 if risk < 0.55 or profile.sandbox else 0.25
        evidence = max(0.0, min(1.0, evidence_score))
        provenance = max(
            0.0, min(1.0, min(profile.provenance_confidence, provenance_score))
        )

        score = (
            0.40 * capability_match
            + 0.20 * protocol_match
            + 0.15 * sandbox_fit
            + 0.15 * evidence
            + 0.10 * provenance
        )
        reasons = [
            f"capability={capability_match:.2f}",
            f"protocol={protocol_match:.2f}",
            f"sandbox_fit={sandbox_fit:.2f}",
            f"evidence={evidence:.2f}",
            f"provenance={provenance:.2f}",
        ]
        return score, reasons

    def rank(
        self,
        required_capabilities: Iterable[str],
        required_protocols: Iterable[str],
        risk: float,
        evidence: dict[str, float] | None = None,
    ) -> list[AgentAssignment]:
        evidence = evidence or {}
        assignments = []
        protocol_registry = ProtocolRegistry(self.repo_root)

        required_protocols = frozenset(required_protocols)
        for profile in self.agents.values():
            if profile.authority != "proposal":
                continue
            if required_protocols and not (required_protocols & profile.protocols):
                continue

            admitted_protocols = []
            for protocol in required_protocols & profile.protocols:
                version = profile.protocol_versions.get(protocol)
                if version is None:
                    continue
                ok, _ = protocol_registry.admit(protocol, version, allow_draft=False)
                if ok:
                    admitted_protocols.append(protocol)
            if required_protocols and not admitted_protocols:
                continue

            score, reasons = self._score(
                profile,
                required_capabilities,
                required_protocols,
                risk,
                float(evidence.get(profile.agent_id, evidence.get("default", 0.5))),
                float(evidence.get(f"provenance:{profile.agent_id}", 1.0)),
            )
            reasons.append("admitted_protocols=" + ",".join(sorted(admitted_protocols)))
            assignments.append(
                AgentAssignment(
                    agent_id=profile.agent_id,
                    score=round(score, 6),
                    reasons=tuple(reasons),
                    profile_digest=digest(profile.as_dict()),
                )
            )

        assignments.sort(key=lambda item: (-item.score, item.agent_id))
        return assignments

    def plan_quorum(
        self,
        required_capabilities: Iterable[str],
        required_protocols: Iterable[str],
        risk: float,
        evidence: dict[str, float] | None = None,
        max_agents: int = 3,
    ) -> QuorumPlan:
        ranked = self.rank(required_capabilities, required_protocols, risk, evidence)
        min_score = float(self.policy.get("minimum_agent_score", 0.70))
        min_provenance = float(self.policy.get("minimum_provenance_confidence", 0.90))

        eligible = []
        seen_families = set()

        for assignment in ranked:
            profile = self.agents[assignment.agent_id]
            if assignment.score < min_score:
                continue
            if profile.provenance_confidence < min_provenance:
                continue
            if profile.family in seen_families:
                continue
            eligible.append(assignment)
            seen_families.add(profile.family)
            if len(eligible) >= max_agents:
                break

        high_risk = risk >= float(self.policy.get("high_risk_threshold", 0.55))
        required = int(
            self.policy.get("high_risk_min_independent_agents", 2)
            if high_risk else 1
        )
        satisfied = len(eligible) >= required

        material = {
            "assignments": [assignment.__dict__ for assignment in eligible],
            "required_independent_families": required,
            "satisfied": satisfied,
        }
        return QuorumPlan(
            assignments=tuple(eligible),
            required_independent_families=required,
            satisfied=satisfied,
            plan_digest=digest(material),
        )

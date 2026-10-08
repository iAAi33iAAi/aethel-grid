#!/usr/bin/env python3
"""
CAIOS bounded evidence council.

The council is advisory. The constitutional gate remains the final authority.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentOpinion:
    role: str
    weight: float
    priority: dict[str, float]
    concerns: tuple[str, ...]
    digest_material: dict[str, Any]


@dataclass(frozen=True)
class CouncilVerdict:
    opinions: tuple[AgentOpinion, ...]
    priority: dict[str, float]
    dissent: tuple[str, ...]
    digest_material: dict[str, Any]


class CouncilAgent:
    role = "agent"
    weight = 1.0

    def advise(self, gaps: dict[str, float], evidence: list[Any]) -> AgentOpinion:
        raise NotImplementedError


class VerificationAgent(CouncilAgent):
    role = "verification"
    weight = 1.20

    def advise(self, gaps, evidence):
        focus = {"conformance": gaps["conformance"], "verification": gaps["verification"]}
        return AgentOpinion(self.role, self.weight, focus, ("proof requires executable evidence",), {"focus": focus})


class SecurityAgent(CouncilAgent):
    role = "security"
    weight = 1.10

    def advise(self, gaps, evidence):
        focus = {"security": gaps["security"], "integration": gaps["integration"] * 0.5}
        return AgentOpinion(self.role, self.weight, focus, ("external tools must be explicit and bounded",), {"focus": focus})


class GovernanceAgent(CouncilAgent):
    role = "governance"
    weight = 1.25

    def advise(self, gaps, evidence):
        focus = {"working_tree": gaps["working_tree"], "conformance": gaps["conformance"] * 0.5}
        return AgentOpinion(self.role, self.weight, focus, ("bootstrap behavior must not become canonical evidence",), {"focus": focus})


class TopologyAgent(CouncilAgent):
    role = "topology"
    weight = 1.05

    def advise(self, gaps, evidence):
        focus = {"integration": gaps["integration"], "verification": gaps["verification"] * 0.5}
        return AgentOpinion(self.role, self.weight, focus, ("repair dependencies before downstream mutation",), {"focus": focus})


class EvidenceAgent(CouncilAgent):
    role = "evidence"
    weight = 1.30

    def advise(self, gaps, evidence):
        observed_failures = sum(1 for item in evidence if getattr(item, "status", "") in {"FAIL", "BLOCKED"})
        focus = {key: value * (1.0 + min(observed_failures, 3) * 0.25) for key, value in gaps.items()}
        return AgentOpinion(self.role, self.weight, focus, ("maximize observable evidence per unit risk",), {"observed_failures": observed_failures})


class CAIOSCouncil:
    def __init__(self, agents: tuple[CouncilAgent, ...] | None = None) -> None:
        self.agents = agents or (
            VerificationAgent(),
            SecurityAgent(),
            GovernanceAgent(),
            TopologyAgent(),
            EvidenceAgent(),
        )

    def deliberate(self, gaps: dict[str, float], evidence: list[Any]) -> CouncilVerdict:
        opinions = tuple(agent.advise(gaps, evidence) for agent in self.agents)
        totals = {key: 0.0 for key in gaps}
        weights = {key: 0.0 for key in gaps}
        for opinion in opinions:
            for key, value in opinion.priority.items():
                if key in totals:
                    totals[key] += float(value) * opinion.weight
                    weights[key] += opinion.weight
        priority = {
            key: (totals[key] / weights[key]) if weights[key] else 0.0
            for key in totals
        }
        ranked = sorted(priority.items(), key=lambda item: (-item[1], item[0]))
        dissent = tuple(
            f"{opinion.role}: {concern}"
            for opinion in opinions
            for concern in opinion.concerns
        )
        return CouncilVerdict(
            opinions=opinions,
            priority=dict(ranked),
            dissent=dissent,
            digest_material={
                "priority": dict(ranked),
                "opinions": [opinion.digest_material for opinion in opinions],
            },
        )

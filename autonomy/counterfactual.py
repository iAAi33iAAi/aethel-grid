#!/usr/bin/env python3
"""
CAIOS counterfactual readiness engine.

Simulates policy-surface changes without touching the repository:
- resolving an invariant
- making a tool available
- establishing canonical conformance
- changing federation/agent/model readiness

This is planning evidence only. It never writes to the repository and never
elevates a scenario to actual readiness.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autonomy.system_readiness import PRIORITY_WEIGHTS, STATUS_GAP


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    changes: dict[str, Any]
    objective: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "changes": self.changes,
            "objective": self.objective,
        }


def scenario_score(baseline: dict[str, Any], scenario: Scenario) -> float:
    readiness = dict(baseline["readiness"])
    blockers = set(baseline["blockers"])
    unresolved = [dict(item) for item in baseline["unresolved_invariants"]]

    changes = scenario.changes

    if changes.get("canonical_conformance") is True:
        readiness["canonical_conformance"] = 1.0
        blockers.discard("canonical-conformance")

    if changes.get("proof_integrity") is True:
        readiness["proof_integrity"] = 1.0
        blockers.discard("proof-integrity")

    if changes.get("proof_graph") is True:
        readiness["proof_graph"] = 1.0
        blockers.discard("proof-graph")

    for invariant_id in changes.get("resolved_invariants", []):
        for item in unresolved:
            if item["id"] == invariant_id:
                item["gap"] = 0.0
        if all(item["id"] != invariant_id for item in unresolved):
            continue

    weighted_gap = 0.0
    weighted_total = 0.0
    for item in unresolved:
        priority = item.get("priority", "medium")
        weight = PRIORITY_WEIGHTS.get(priority, 0.5)
        weighted_total += weight
        weighted_gap += item.get("gap", 1.0) * weight

    pfp = 1.0 - (weighted_gap / weighted_total if weighted_total else 0.0)
    readiness["pfp_declared_completeness"] = round(pfp, 6)

    raw = sum(float(value) for value in readiness.values()) / max(1, len(readiness))
    blocker_penalty = min(0.75, 0.10 * len(blockers))
    return round(max(0.0, min(1.0, raw - blocker_penalty)), 6)


def rank_scenarios(
    baseline: dict[str, Any],
    scenarios: tuple[Scenario, ...],
) -> list[dict[str, Any]]:
    current = sum(float(v) for v in baseline["readiness"].values()) / max(
        1, len(baseline["readiness"])
    )
    ranked = []
    for scenario in scenarios:
        future = scenario_score(baseline, scenario)
        ranked.append({
            **scenario.as_dict(),
            "baseline_score": round(current, 6),
            "counterfactual_score": future,
            "delta": round(future - current, 6),
        })
    return sorted(ranked, key=lambda row: (-row["delta"], row["scenario_id"]))

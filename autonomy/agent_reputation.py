#!/usr/bin/env python3
"""
CAIOS evidence-based agent reputation.

Reputation affects selection priority only. It can never elevate an agent's
authority level or bypass the constitutional gate.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class AgentReputationStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except json.JSONDecodeError:
                continue
        return rows

    def record(
        self,
        agent_id: str,
        *,
        action_kind: str,
        outcome: str,
        test_pass: bool | None,
        evidence_gain: float,
        risk: float,
        rollback: bool = False,
    ) -> None:
        row = {
            "agent_id": agent_id,
            "action_kind": action_kind,
            "outcome": outcome,
            "test_pass": test_pass,
            "evidence_gain": max(0.0, min(1.0, float(evidence_gain))),
            "risk": max(0.0, min(1.0, float(risk))),
            "rollback": bool(rollback),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    def score(self, agent_id: str) -> float:
        rows = [row for row in self._read() if row.get("agent_id") == agent_id]
        if not rows:
            return 0.5

        weighted_total = 0.0
        weight_total = 0.0
        for index, row in enumerate(rows[-20:], start=1):
            weight = 0.85 ** (len(rows[-20:]) - index)
            outcome_score = {
                "PASS": 1.0,
                "CONTINUE": 0.75,
                "BLOCKED": 0.40,
                "FAIL": 0.0,
            }.get(str(row.get("outcome")), 0.25)

            test_pass = row.get("test_pass")
            test_score = (
                1.0 if test_pass is True else 0.0 if test_pass is False else 0.5
            )
            evidence_score = float(row.get("evidence_gain", 0.0))
            risk = float(row.get("risk", 0.0))
            rollback = bool(row.get("rollback", False))

            sample = (
                0.45 * outcome_score
                + 0.25 * test_score
                + 0.20 * evidence_score
                + 0.10 * (1.0 - risk)
            )
            if rollback:
                sample *= 0.25
            weighted_total += weight * max(0.0, min(1.0, sample))
            weight_total += weight

        score = weighted_total / weight_total if weight_total else 0.5
        return round(max(0.0, min(1.0, score)), 6)

    def all_scores(self) -> dict[str, float]:
        ids = sorted({str(row.get("agent_id")) for row in self._read() if row.get("agent_id")})
        return {agent_id: self.score(agent_id) for agent_id in ids}

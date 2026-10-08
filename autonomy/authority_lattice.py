#!/usr/bin/env python3
"""
CAIOS authority lattice.

Separates provenance/origin from execution authority. An agent may have a
capability without possessing the authority to exercise that capability.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path


class AuthorityLevel(IntEnum):
    OBSERVE = 0
    ADVISORY = 10
    EVIDENCE = 20
    POLICY = 30
    EXECUTION = 40
    HUMAN = 50


@dataclass(frozen=True)
class Principal:
    principal_id: str
    authority: AuthorityLevel
    capabilities: frozenset[str]
    boundary: str

    def as_dict(self) -> dict[str, object]:
        return {
            "principal_id": self.principal_id,
            "authority": int(self.authority),
            "authority_name": self.authority.name,
            "capabilities": sorted(self.capabilities),
            "boundary": self.boundary,
        }


REQUIRED_LEVELS = {
    "observe": AuthorityLevel.OBSERVE,
    "propose": AuthorityLevel.ADVISORY,
    "evidence": AuthorityLevel.EVIDENCE,
    "policy": AuthorityLevel.POLICY,
    "execute": AuthorityLevel.EXECUTION,
    "human-final": AuthorityLevel.HUMAN,
}


class AuthorityLattice:
    def __init__(self, repo_root: Path, path: str = "autonomy/authority_lattice.json") -> None:
        raw = json.loads((repo_root / path).read_text(encoding="utf-8"))
        self.principals = {
            item["principal_id"]: Principal(
                principal_id=str(item["principal_id"]),
                authority=AuthorityLevel(int(item["authority"])),
                capabilities=frozenset(item.get("capabilities", [])),
                boundary=str(item.get("boundary", "")),
            )
            for item in raw.get("principals", [])
        }

    def get(self, principal_id: str) -> Principal | None:
        return self.principals.get(principal_id)

    def authorize(self, principal_id: str, capability: str) -> tuple[bool, str]:
        principal = self.get(principal_id)
        if principal is None:
            return False, "principal-not-registered"
        required = REQUIRED_LEVELS.get(capability)
        if required is None:
            return False, "capability-requirement-undefined"
        if capability not in principal.capabilities:
            return False, "capability-not-granted"
        if principal.authority < required:
            return False, "authority-level-insufficient"
        return True, "authorized"

    def explain(self) -> dict[str, object]:
        return {
            "schema": "caios-authority-lattice/v1",
            "required_levels": {key: int(value) for key, value in REQUIRED_LEVELS.items()},
            "principals": [item.as_dict() for item in self.principals.values()],
        }

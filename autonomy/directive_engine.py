#!/usr/bin/env python3
"""
CAIOS directive engine.

Turns readiness blockers into an ordered work queue with explicit authority
requirements. The engine never fabricates missing specification semantics.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autonomy.system_readiness import evaluate as evaluate_readiness
from autonomy.counterfactual import Scenario, rank_scenarios


@dataclass(frozen=True)
class Directive:
    directive_id: str
    priority: str
    objective: str
    authority: str
    autonomous: bool
    prerequisites: tuple[str, ...]
    evidence_target: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "directive_id": self.directive_id,
            "priority": self.priority,
            "objective": self.objective,
            "authority": self.authority,
            "autonomous": self.autonomous,
            "prerequisites": list(self.prerequisites),
            "evidence_target": self.evidence_target,
        }


CRITICAL_PROTOCOL_ACTIONS = {
    "INV-006": Directive(
        "INV-006",
        "critical",
        "Establish immutable KernelManifest issuance and persistent seal history.",
        "governance",
        False,
        ("federation manifest", "persistent seal store"),
        "immutable-manifest-record",
    ),
    "INV-007": Directive(
        "INV-007",
        "critical",
        "Bind AuditRecord signatures to an approved Ed25519 or external signing authority.",
        "security",
        False,
        ("node identity", "signing-key policy"),
        "signed-audit-record",
    ),
    "INV-013": Directive(
        "INV-013",
        "critical",
        "Require a session anchor to be accepted before an autonomous action begins.",
        "caios",
        True,
        ("session anchor registry",),
        "session-anchor",
    ),
    "INV-014": Directive(
        "INV-014",
        "critical",
        "Enforce authenticated transport for every inter-service federation channel.",
        "security",
        False,
        ("mTLS policy", "service certificate authority"),
        "mTLS-handshake-evidence",
    ),
    "INV-019": Directive(
        "INV-019",
        "critical",
        "Require explicit cross-namespace authorization before data or action flow.",
        "policy",
        False,
        ("namespace registry", "authorization policy"),
        "namespace-authorization-decision",
    ),
}


def build_directives(repo_root: Path) -> dict[str, Any]:
    readiness = evaluate_readiness(repo_root)
    directives: list[Directive] = []

    for unresolved in readiness["unresolved_invariants"]:
        invariant_id = unresolved["id"]
        if invariant_id in CRITICAL_PROTOCOL_ACTIONS:
            directives.append(CRITICAL_PROTOCOL_ACTIONS[invariant_id])

    if "canonical-conformance" in readiness["blockers"]:
        directives.append(
            Directive(
                "SPEC-004",
                "critical",
                "Acquire authoritative SPEC-004 validator, encoding rules, audit-preimage semantics, and TV-001..TV-007 vectors.",
                "human/spec-authority",
                False,
                ("authoritative source material",),
                "canonical-conformance-pass",
            )
        )

    if "federation-manifest-seal" in readiness["blockers"]:
        directives.append(
            Directive(
                "FED-MANIFEST-SEAL",
                "high",
                "Generate and verify the topology manifest seal before relying on the federation graph.",
                "caios",
                True,
                ("federation/system_manifest.json",),
                "federation-manifest-seal",
            )
        )

    if "proof-integrity" in readiness["blockers"]:
        directives.append(
            Directive(
                "PROOF-CHAIN",
                "high",
                "Generate and independently verify a current CAIOS certificate chain.",
                "caios",
                True,
                ("autonomous runtime",),
                "proof-chain-pass",
            )
        )

    seen = set()
    ordered = []
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for directive in sorted(
        directives,
        key=lambda item: (priority_order.get(item.priority, 9), item.directive_id),
    ):
        if directive.directive_id not in seen:
            ordered.append(directive)
            seen.add(directive.directive_id)

    scenarios = (
        Scenario(
            "establish-canonical-conformance",
            {"canonical_conformance": True},
            "establish authoritative SPEC-004 conformance evidence",
        ),
        Scenario(
            "complete-critical-invariants",
            {"resolved_invariants": [item["id"] for item in readiness["unresolved_invariants"] if item["priority"] == "critical"]},
            "resolve declared critical protocol gaps",
        ),
        Scenario(
            "complete-proof-surface",
            {"proof_integrity": True, "proof_graph": True},
            "complete local proof materialization",
        ),
    )
    counterfactuals = rank_scenarios(readiness, scenarios)

    material = {
        "schema": "caios-directive-plan/v1",
        "readiness_digest": readiness["readiness_digest"],
        "directives": [item.as_dict() for item in ordered],
        "counterfactuals": counterfactuals,
    }

    from autonomy.evidence_bundle import digest

    return {
        **material,
        "directive_digest": digest(material),
        "next_directive": ordered[0].as_dict() if ordered else None,
    }


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="build CAIOS directive plan")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="ops/caios/directive-plan.json")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    result = build_directives(root)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

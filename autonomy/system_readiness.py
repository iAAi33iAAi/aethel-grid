#!/usr/bin/env python3
"""
CAIOS system readiness director.

Combines declared protocol gaps with live machine evidence to produce a
bounded readiness vector and the highest-value next inspection target.

Declared protocol status is never upgraded to PASS merely because the local
runtime is healthy.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from autonomy.evidence_bundle import digest
from autonomy.verify_certificates import verify
from conformance.contract import inspect_contract


PRIORITY_WEIGHTS = {
    "critical": 1.00,
    "high": 0.75,
    "medium": 0.50,
    "low": 0.25,
}

STATUS_GAP = {
    "satisfied": 0.0,
    "partial": 0.5,
    "not_implemented": 1.0,
}


def load_registry(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "conformance" / "federated_invariant_registry.json"
    if not path.is_file():
        return {
            "invariants": [],
            "_missing": True,
            "_path": str(path.relative_to(repo_root)),
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "invariants": [],
            "_invalid": True,
            "_path": str(path.relative_to(repo_root)),
        }


def evaluate(repo_root: Path) -> dict[str, Any]:
    contract = inspect_contract(repo_root)
    certificate_path = repo_root / "ops/caios/autonomy-certificates.jsonl"
    proof_graph = repo_root / "ops/caios/proof-graph.json"
    federation = repo_root / "ops/caios/federation-snapshot.json"
    agents = repo_root / "autonomy/agent_registry.json"
    tools = repo_root / "integrations/caios_tool_registry.json"

    invariant_registry = load_registry(repo_root)
    invariants = invariant_registry.get("invariants", [])

    unresolved = []
    weighted_total = 0.0
    weighted_gap = 0.0

    for invariant in invariants:
        gap = STATUS_GAP.get(invariant.get("declared_status", "not_implemented"), 1.0)
        weight = PRIORITY_WEIGHTS.get(invariant.get("priority", "medium"), 0.5)
        weighted_total += weight
        weighted_gap += gap * weight
        if gap > 0:
            unresolved.append(
                {
                    "id": invariant["id"],
                    "domain": invariant["domain"],
                    "priority": invariant["priority"],
                    "definition": invariant["definition"],
                    "gap": gap,
                }
            )

    pfp_score = 1.0 - (weighted_gap / weighted_total if weighted_total else 1.0)

    proof_ok = certificate_path.is_file() and verify(certificate_path)[0]
    operational = proof_ok and proof_graph.is_file()
    federation_ok = federation.is_file()
    agents_ok = agents.is_file()
    tools_ok = tools.is_file()

    readiness = {
        "causal_runtime": 1.0,
        "proof_integrity": 1.0 if proof_ok else 0.0,
        "proof_graph": 1.0 if proof_graph.is_file() else 0.0,
        "canonical_conformance": 1.0 if contract.status == "PASS" else 0.0,
        "federation_observability": 1.0 if federation_ok else 0.0,
        "agent_registry": 1.0 if agents_ok else 0.0,
        "tool_registry": 1.0 if tools_ok else 0.0,
        "pfp_declared_completeness": round(pfp_score, 6),
    }

    blockers = [
        "federated-invariant-registry-missing" if invariant_registry.get("_missing") else None,
        "federated-invariant-registry-invalid" if invariant_registry.get("_invalid") else None,
        "canonical-conformance"
        if contract.status != "PASS"
        else None,
        "proof-integrity" if not proof_ok else None,
        "proof-graph" if not proof_graph.is_file() else None,
        "critical-protocol-invariants"
        if any(item["priority"] == "critical" and item["gap"] > 0 for item in unresolved)
        else None,
    ]
    blockers = [item for item in blockers if item]

    unresolved.sort(
        key=lambda item: (-PRIORITY_WEIGHTS[item["priority"]], -item["gap"], item["id"])
    )

    bundle_material = {
        "readiness": readiness,
        "blockers": blockers,
        "unresolved": unresolved,
        "conformance_digest": contract.contract_digest,
    }

    return {
        "schema": "caios-system-readiness/v1",
        "mode": "HOLD" if blockers else "READY",
        "operational": operational,
        "canonical": contract.status == "PASS" and not blockers,
        "readiness": readiness,
        "blockers": blockers,
        "next_inspection_target": unresolved[0] if unresolved else None,
        "unresolved_invariants": unresolved,
        "contract": contract.as_dict(),
        "readiness_digest": digest(bundle_material),
    }


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="CAIOS system readiness director")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="ops/caios/system-readiness.json")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    result = evaluate(root)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

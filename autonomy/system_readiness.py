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
from federation.security_primitives import ManifestSeal, ManifestSealer


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
    relative_path = str(path.relative_to(repo_root))
    if not path.is_file():
        return {
            "invariants": [],
            "_missing": True,
            "_path": relative_path,
        }
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "invariants": [],
            "_invalid": True,
            "_error": "unreadable-or-invalid-json",
            "_path": relative_path,
        }

    # Treat registry data as untrusted input. Never allow malformed fields or
    # unknown scoring enums to crash the readiness report or silently alter it.
    if not isinstance(registry, dict):
        valid = False
    else:
        valid = isinstance(registry.get("invariants"), list)
        if valid:
            for invariant in registry["invariants"]:
                if not isinstance(invariant, dict):
                    valid = False
                    break
                required = ("id", "domain", "priority", "declared_status", "definition")
                if any(
                    not isinstance(invariant.get(key), str) or not invariant[key].strip()
                    for key in required
                ):
                    valid = False
                    break
                if invariant["priority"] not in PRIORITY_WEIGHTS:
                    valid = False
                    break
                if invariant["declared_status"] not in STATUS_GAP:
                    valid = False
                    break

    if not valid:
        return {
            "invariants": [],
            "_invalid": True,
            "_error": "registry-shape-or-enum-invalid",
            "_path": relative_path,
        }
    return registry


def evaluate(repo_root: Path) -> dict[str, Any]:
    contract = inspect_contract(repo_root)
    certificate_path = repo_root / "ops/caios/autonomy-certificates.jsonl"
    proof_graph = repo_root / "ops/caios/proof-graph.json"
    federation = repo_root / "ops/caios/federation-snapshot.json"
    agents = repo_root / "autonomy/agent_registry.json"
    tools = repo_root / "integrations/caios_tool_registry.json"
    session_anchors = repo_root / "ops/caios/session-anchors.jsonl"
    manifest_seal_path = repo_root / "ops/caios/federation-manifest-seal.json"
    invariant_evidence_path = repo_root / "conformance/invariant_evidence_map.json"

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

    manifest_seal_ok = False
    manifest_seal_reason = "missing"
    federation_manifest = repo_root / "federation/system_manifest.json"
    if manifest_seal_path.is_file() and federation_manifest.is_file():
        try:
            seal_row = json.loads(manifest_seal_path.read_text(encoding="utf-8"))
            seal = ManifestSeal(**seal_row["seal"])
            manifest = json.loads(federation_manifest.read_text(encoding="utf-8"))
            manifest_seal_ok, manifest_seal_reason = ManifestSealer.verify(manifest, seal)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            manifest_seal_reason = f"invalid:{type(exc).__name__}"

    invariant_evidence = {}
    if invariant_evidence_path.is_file():
        try:
            invariant_evidence = json.loads(
                invariant_evidence_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            invariant_evidence = {"_invalid": True}

    proof_ok = certificate_path.is_file() and verify(certificate_path)[0]
    operational = proof_ok and proof_graph.is_file()
    federation_ok = federation.is_file()
    agents_ok = agents.is_file()
    tools_ok = tools.is_file()

    readiness = {
        "causal_runtime": 1.0 if operational else 0.0,
        "proof_integrity": 1.0 if proof_ok else 0.0,
        "proof_graph": 1.0 if proof_graph.is_file() else 0.0,
        "canonical_conformance": 1.0 if contract.status == "PASS" else 0.0,
        "federation_observability": 1.0 if federation_ok else 0.0,
        "agent_registry": 1.0 if agents_ok else 0.0,
        "tool_registry": 1.0 if tools_ok else 0.0,
        "session_anchor_surface": 1.0 if session_anchors.is_file() else 0.0,
        "federation_manifest_seal": 1.0 if manifest_seal_ok else 0.0,
        "invariant_evidence_map": 1.0 if invariant_evidence_path.is_file() and not invariant_evidence.get("_invalid") else 0.0,
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
        "federation-manifest-seal" if federation_manifest.is_file() and not manifest_seal_ok else None,
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
        "manifest_seal": {
            "present": manifest_seal_path.is_file(),
            "verified": manifest_seal_ok,
            "reason": manifest_seal_reason,
        },
        "invariant_evidence": invariant_evidence,
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

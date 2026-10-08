#!/usr/bin/env python3
"""
CAIOS system knowledge graph.

Builds a deterministic graph from repository federation, PFP invariants,
agent registry, tool registry, and current readiness state.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from autonomy.evidence_bundle import digest
from autonomy.system_readiness import evaluate as evaluate_readiness
from autonomy.protocol_conformance import ProtocolConformanceRunner
from autonomy.supply_chain_plan import build_plan as build_supply_chain_plan


def build_graph(repo_root: Path) -> dict[str, Any]:
    readiness = evaluate_readiness(repo_root)
    federation_path = repo_root / "federation" / "system_manifest.json"
    agent_path = repo_root / "autonomy" / "agent_registry.json"
    tool_path = repo_root / "integrations" / "caios_tool_registry.json"
    invariant_path = repo_root / "conformance" / "federated_invariant_registry.json"
    authority_path = repo_root / "autonomy" / "authority_lattice.json"
    model_path = repo_root / "autonomy" / "model_registry.json"
    invariant_evidence_path = repo_root / "conformance" / "invariant_evidence_map.json"

    federation = json.loads(federation_path.read_text(encoding="utf-8")) if federation_path.is_file() else {}
    agents = json.loads(agent_path.read_text(encoding="utf-8")) if agent_path.is_file() else {}
    tools = json.loads(tool_path.read_text(encoding="utf-8")) if tool_path.is_file() else {}
    invariants = json.loads(invariant_path.read_text(encoding="utf-8")) if invariant_path.is_file() else {}
    authorities = json.loads(authority_path.read_text(encoding="utf-8")) if authority_path.is_file() else {}
    models = json.loads(model_path.read_text(encoding="utf-8")) if model_path.is_file() else {}
    invariant_evidence = json.loads(
        invariant_evidence_path.read_text(encoding="utf-8")
    ) if invariant_evidence_path.is_file() else {}

    nodes = []
    edges = []

    for repository in federation.get("repositories", []):
        repo_id = f"repo:{repository['id']}"
        nodes.append({
            "id": repo_id,
            "kind": "repository",
            "label": repository["id"],
            "status": repository.get("status"),
            "role": repository.get("role"),
        })

    for repository in federation.get("repositories", []):
        for dependency in repository.get("depends_on", []):
            edges.append({
                "source": f"repo:{repository['id']}",
                "target": f"repo:{dependency}",
                "relation": "depends-on",
            })

    for invariant in invariants.get("invariants", []):
        node_id = f"invariant:{invariant['id']}"
        nodes.append({
            "id": node_id,
            "kind": "invariant",
            "label": invariant["id"],
            "domain": invariant["domain"],
            "priority": invariant["priority"],
            "declared_status": invariant["declared_status"],
        })
        edges.append({
            "source": node_id,
            "target": "system:readiness",
            "relation": "constrains",
        })

    for agent in agents.get("agents", []):
        agent_id = f"agent:{agent['id']}"
        nodes.append({
            "id": agent_id,
            "kind": "agent",
            "label": agent["id"],
            "family": agent["family"],
            "protocols": sorted(agent.get("protocols", [])),
            "capabilities": sorted(agent.get("capabilities", [])),
            "authority": agent.get("authority"),
        })
        edges.append({
            "source": agent_id,
            "target": "system:caios",
            "relation": "advises",
        })

    for principal in authorities.get("principals", []):
        principal_id = f"authority:{principal['principal_id']}"
        nodes.append({
            "id": principal_id,
            "kind": "authority",
            "label": principal["principal_id"],
            "level": principal.get("authority"),
            "boundary": principal.get("boundary"),
        })
        edges.append({
            "source": principal_id,
            "target": "system:caios",
            "relation": "authority-boundary",
        })

    for model in models.get("models", []):
        model_id = f"model:{model['model_id']}"
        nodes.append({
            "id": model_id,
            "kind": "model",
            "label": model["model_id"],
            "class": model.get("class"),
            "weight_license": model.get("weight_license"),
            "production": model.get("production"),
        })
        edges.append({
            "source": model_id,
            "target": "system:caios",
            "relation": "proposal-input",
        })

    for invariant_id, evidence in invariant_evidence.get("entries", {}).items():
        evidence_id = f"mechanism:{invariant_id}"
        nodes.append({
            "id": evidence_id,
            "kind": "mechanism",
            "label": evidence.get("implementation", invariant_id),
            "state": evidence.get("state"),
            "basis": evidence.get("basis"),
        })
        edges.append({
            "source": evidence_id,
            "target": f"invariant:{invariant_id}",
            "relation": "implements-mechanism",
        })

    security_artifacts = (
        ("artifact:session-anchors", "session-anchor-log", "ops/caios/session-anchors.jsonl"),
        ("artifact:manifest-seal", "federation-manifest-seal", "ops/caios/federation-manifest-seal.json"),
    )
    for artifact_id, label, relative in security_artifacts:
        nodes.append({
            "id": artifact_id,
            "kind": "security-artifact",
            "label": label,
            "present": (repo_root / relative).is_file(),
            "path": relative,
        })
        edges.append({
            "source": artifact_id,
            "target": "system:caios",
            "relation": "evidence-input",
        })

    for tool in tools.get("tools", []):
        tool_id = f"tool:{tool['id']}"
        nodes.append({
            "id": tool_id,
            "kind": "tool",
            "label": tool["id"],
            "capability": tool.get("capability"),
            "authority": tool.get("authority"),
            "license": tool.get("license"),
        })
        edges.append({
            "source": tool_id,
            "target": "system:caios",
            "relation": "adapter",
        })

    protocol_plan = ProtocolConformanceRunner(repo_root).plan()
    for item in protocol_plan:
        protocol_id = f"protocol:{item['protocol']}"
        nodes.append({
            "id": protocol_id,
            "kind": "protocol",
            "label": item["protocol"],
            "revision": item["revision"],
            "status": item["status"],
            "conformance": item["conformance"],
        })
        edges.append({
            "source": protocol_id,
            "target": "system:caios",
            "relation": "transport-surface",
        })

    supply_chain = build_supply_chain_plan(repo_root)
    for check in supply_chain["checks"]:
        check_id = f"supply:{check['check_id']}"
        nodes.append({
            "id": check_id,
            "kind": "supply-chain-check",
            "label": check["check_id"],
            "standard": check["standard"],
            "tool_id": check["tool_id"],
            "required": check["required"],
            "available": check["available"],
        })
        edges.append({
            "source": check_id,
            "target": f"tool:{check['tool_id']}",
            "relation": "verified-by",
        })

    nodes.append({
        "id": "system:caios",
        "kind": "system",
        "label": "CAIOS",
        "mode": "HOLD" if readiness["mode"] == "HOLD" else "READY",
    })
    nodes.append({
        "id": "system:readiness",
        "kind": "readiness",
        "label": "CAIOS System Readiness",
        "mode": readiness["mode"],
        "readiness": readiness["readiness"],
        "blockers": readiness["blockers"],
        "next_inspection_target": readiness["next_inspection_target"],
    })

    material = {
        "schema": "caios-system-knowledge-graph/v1",
        "nodes": sorted(nodes, key=lambda x: x["id"]),
        "edges": sorted(edges, key=lambda x: (x["source"], x["target"], x["relation"])),
        "readiness_digest": readiness["readiness_digest"],
    }
    return {
        **material,
        "graph_digest": digest(material),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="build CAIOS system knowledge graph")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="ops/caios/system-knowledge-graph.json")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    result = build_graph(root)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

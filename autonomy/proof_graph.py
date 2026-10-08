#!/usr/bin/env python3
"""
CAIOS proof/evidence graph.

Converts one runtime cycle into a deterministic directed evidence graph:
observation -> gaps -> council -> action -> evidence -> certificate.

The graph is an explanation artifact. It does not grant execution authority.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    kind: str
    digest: str
    attributes: dict[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: str


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def build_proof_graph(certificate: dict[str, Any]) -> dict[str, Any]:
    proof = str(certificate.get("proof_digest", ""))
    observation = str(certificate.get("observation_digest", ""))
    council = str(certificate.get("council_digest", ""))
    action = str(certificate.get("action_fingerprint") or "")

    nodes = [
        GraphNode("observation", "observation", observation, {"cycle": certificate.get("cycle")}),
        GraphNode("council", "council", council, {"roles": [e.get("details", {}).get("roles", []) for e in certificate.get("evidence", []) if e.get("kind") == "council"]}),
        GraphNode("action", "action", action, {"selected_action": certificate.get("selected_action")}),
        GraphNode("certificate", "certificate", proof, {"decision": certificate.get("decision")}),
    ]
    for index, evidence in enumerate(certificate.get("evidence", [])):
        nodes.append(
            GraphNode(
                f"evidence-{index}",
                str(evidence.get("kind", "evidence")),
                str(evidence.get("digest", "")),
                {"status": evidence.get("status"), "source": evidence.get("source")},
            )
        )

    edges = [
        GraphEdge("observation", "council", "informs"),
        GraphEdge("council", "action", "prioritizes"),
        GraphEdge("action", "certificate", "certified-by"),
    ]
    for index in range(len(certificate.get("evidence", []))):
        edges.append(GraphEdge(f"evidence-{index}", "certificate", "supports"))

    previous = certificate.get("previous_certificate_digest")
    if previous:
        nodes.append(GraphNode("previous-certificate", "certificate", str(previous), {"chain": "previous"}))
        edges.append(GraphEdge("previous-certificate", "certificate", "chains-to"))

    material = {
        "schema": "caios-proof-graph/v1",
        "nodes": [node.__dict__ for node in nodes],
        "edges": [edge.__dict__ for edge in edges],
    }
    return {
        **material,
        "graph_digest": digest(material),
    }


def graph_from_jsonl(path, output=None) -> dict[str, Any]:
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    graphs = [build_proof_graph(row) for row in rows]
    result = {"schema": "caios-proof-graph-chain/v1", "graphs": graphs, "chain_digest": digest(graphs)}
    if output:
        with open(output, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="build CAIOS proof graph")
    parser.add_argument("certificates")
    parser.add_argument("--output", default="ops/caios/proof-graph.json")
    args = parser.parse_args()
    result = graph_from_jsonl(args.certificates, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))

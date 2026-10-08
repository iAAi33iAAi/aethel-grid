from pathlib import Path
import json

from autonomy.system_knowledge_graph import build_graph


def test_system_graph_binds_repositories_agents_tools_and_invariants(tmp_path: Path):
    (tmp_path / "federation").mkdir()
    (tmp_path / "autonomy").mkdir()
    (tmp_path / "integrations").mkdir()
    (tmp_path / "conformance").mkdir()

    (tmp_path / "federation/system_manifest.json").write_text(json.dumps({
        "repositories": [
            {"id": "core", "role": "core", "path": ".", "depends_on": []}
        ]
    }), encoding="utf-8")
    (tmp_path / "autonomy/protocol_registry.json").write_text(json.dumps({
        "policy": {"draft_protocol_requires_opt_in": True},
        "protocols": [{
            "id": "acp",
            "latest_known_revision": "1",
            "status": "stable",
            "transport_role": "agent-client",
            "license": "Apache-2.0",
            "source_url": "https://example.invalid/acp",
            "draft": False
        }]
    }), encoding="utf-8")
    (tmp_path / "autonomy/agent_registry.json").write_text(json.dumps({
        "agents": [
            {"id": "a", "family": "a", "protocols": ["acp"], "capabilities": ["coding"], "authority": "proposal"}
        ],
        "selection_policy": {}
    }), encoding="utf-8")
    (tmp_path / "integrations/caios_tool_registry.json").write_text(json.dumps({
        "tools": [
            {"id": "t", "capability": "verification", "authority": "evidence", "license": "MIT"}
        ],
        "policy": {}
    }), encoding="utf-8")
    (tmp_path / "conformance/federated_invariant_registry.json").write_text(json.dumps({
        "invariants": [
            {"id": "INV-001", "domain": "test", "priority": "critical", "declared_status": "not_implemented", "definition": "x"}
        ]
    }), encoding="utf-8")
    (tmp_path / "conformance/canonical_contract.json").write_text(json.dumps({
        "schema": "caios-conformance/v1",
        "spec_id": "SPEC-004",
        "canonical_encoding": None,
        "audit_preimage_semantics": None,
        "canonical_validator": {"path": None, "command": [], "sha256": None},
        "required_vectors": [{"id": f"TV-{i:03d}", "path": None, "sha256": None} for i in range(1,8)],
        "promotion_policy": {"bootstrap_must_never_promote_to_canonical": True}
    }), encoding="utf-8")

    graph = build_graph(tmp_path)
    kinds = {node["kind"] for node in graph["nodes"]}
    assert {"repository", "agent", "tool", "invariant", "system", "readiness"} <= kinds
    assert graph["graph_digest"]

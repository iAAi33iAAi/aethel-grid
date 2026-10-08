from pathlib import Path

from autonomy.agent_router import AgentRegistry


def test_router_prefers_capability_fit(tmp_path: Path):
    registry = tmp_path / "autonomy"
    registry.mkdir()
    (registry / "protocol_registry.json").write_text(
        """{
          "policy": {"draft_protocol_requires_opt_in": true, "major_version_mismatch": "REJECT"},
          "protocols": [
            {
              "id":"acp",
              "latest_known_revision":"1",
              "status":"stable",
              "transport_role":"agent-client",
              "license":"Apache-2.0",
              "source_url":"https://github.com/agentclientprotocol/agent-client-protocol",
              "draft":false
            },
            {
              "id":"mcp",
              "latest_known_revision":"2026-07-28",
              "status":"final",
              "transport_role":"agent-to-tool-context",
              "license":"MIT",
              "source_url":"https://modelcontextprotocol.io/",
              "draft":false
            }
          ]
        }""",
        encoding="utf-8",
    )
    (registry / "agent_registry.json").write_text(
        """{
          "selection_policy": {},
          "agents": [
            {"id":"coder","family":"coder","protocols":["acp"],"protocol_versions":{"acp":"1"},"capabilities":["coding","testing"],"authority":"proposal","license":"MIT","sandbox":true,"provenance_confidence":1.0},
            {"id":"planner","family":"planner","protocols":["mcp"],"protocol_versions":{"mcp":"2026-07-28"},"capabilities":["planning"],"authority":"proposal","license":"MIT","sandbox":false,"provenance_confidence":1.0}
          ]
        }""",
        encoding="utf-8",
    )
    r = AgentRegistry(tmp_path).rank(["coding","testing"], ["acp"], 0.4)
    assert r[0].agent_id == "coder"


def test_high_risk_requires_independent_families(tmp_path: Path):
    registry = tmp_path / "autonomy"
    registry.mkdir()
    (registry / "protocol_registry.json").write_text(
        """{
          "policy": {"draft_protocol_requires_opt_in": true, "major_version_mismatch": "REJECT"},
          "protocols": [
            {
              "id":"acp",
              "latest_known_revision":"1",
              "status":"stable",
              "transport_role":"agent-client",
              "license":"Apache-2.0",
              "source_url":"https://github.com/agentclientprotocol/agent-client-protocol",
              "draft":false
            },
            {
              "id":"mcp",
              "latest_known_revision":"2026-07-28",
              "status":"final",
              "transport_role":"agent-to-tool-context",
              "license":"MIT",
              "source_url":"https://modelcontextprotocol.io/",
              "draft":false
            }
          ]
        }""",
        encoding="utf-8",
    )
    (registry / "agent_registry.json").write_text(
        """{
          "selection_policy": {"high_risk_threshold":0.55,"high_risk_min_independent_agents":2,"minimum_protocol_confidence":0.0,"minimum_provenance_confidence":0.9},
          "agents": [
            {"id":"one","family":"family-one","protocols":["acp"],"protocol_versions":{"acp":"1"},"capabilities":["coding"],"authority":"proposal","license":"MIT","sandbox":true,"provenance_confidence":1.0},
            {"id":"one-alt","family":"family-one","protocols":["acp"],"protocol_versions":{"acp":"1"},"capabilities":["coding"],"authority":"proposal","license":"MIT","sandbox":true,"provenance_confidence":1.0}
          ]
        }""",
        encoding="utf-8",
    )
    plan = AgentRegistry(tmp_path).plan_quorum(["coding"], ["acp"], 0.8, max_agents=3)
    assert plan.required_independent_families == 2
    assert plan.satisfied is False

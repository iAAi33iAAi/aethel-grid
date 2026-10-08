from pathlib import Path

from autonomy.agent_router import AgentRegistry


def test_router_prefers_capability_fit(tmp_path: Path):
    registry = tmp_path / "autonomy"
    registry.mkdir()
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

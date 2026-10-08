from pathlib import Path
import json

from autonomy.supply_chain_plan import build_plan


def test_supply_chain_plan_binds_current_security_standards(tmp_path: Path):
    (tmp_path / "integrations").mkdir()
    (tmp_path / "integrations/caios_tool_registry.json").write_text(
        json.dumps({
            "policy": {},
            "tools": [
                {"id":"cosign","capability":"artifact-signing","authority":"cryptographic","license":"Apache-2.0"},
                {"id":"syft","capability":"sbom","authority":"evidence","license":"Apache-2.0"},
                {"id":"grype","capability":"vulnerability-scan","authority":"evidence","license":"Apache-2.0"},
                {"id":"in-toto","capability":"provenance-attestation","authority":"cryptographic","license":"Apache-2.0"},
                {"id":"scorecard","capability":"supply-chain-security","authority":"evidence","license":"Apache-2.0"},
                {"id":"opa","capability":"policy-evaluation","authority":"deterministic","license":"Apache-2.0"},
                {"id":"otel","capability":"telemetry","authority":"evidence","license":"Apache-2.0"}
            ]
        }),
        encoding="utf-8",
    )
    plan = build_plan(tmp_path)
    assert plan["schema"] == "caios-supply-chain-plan/v1"
    assert plan["standards"]["slsa"] == "1.2"
    assert plan["standards"]["attestation"] == "in-toto/DSSE"
    assert plan["plan_digest"]


def test_required_tools_without_commands_are_blockers(tmp_path: Path):
    (tmp_path / "integrations").mkdir()
    (tmp_path / "integrations/caios_tool_registry.json").write_text(
        json.dumps({"policy": {}, "tools": []}),
        encoding="utf-8",
    )
    plan = build_plan(tmp_path)
    assert "slsa-provenance" in plan["blockers"]
    assert "sbom" in plan["blockers"]
    assert "vulnerability" in plan["blockers"]

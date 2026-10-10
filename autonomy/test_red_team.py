from pathlib import Path
import json

from autonomy.red_team import probes, run_campaign


def test_red_team_campaign_denies_all_probes(tmp_path: Path):
    autonomy = tmp_path / "autonomy"
    autonomy.mkdir(parents=True)
    (autonomy / "protected_surfaces.json").write_text(
        json.dumps({
            "protected_globs": [
                "autonomy/agent_registry.json",
                "autonomy/model_registry.json",
                "autonomy/protocol_registry.json",
                "autonomy/test_registered_agent_source_pins.py",
                "docs/CAIOS-OPENAI-COMPATIBLE-PROPOSAL-TRANSPORT.md"
            ]
        }),
        encoding="utf-8",
    )
    existing_test = autonomy / "test_sandbox_simulator.py"
    existing_test.write_text("def test_fixture(): pass\\n", encoding="utf-8")

    inventory = probes()
    probe_ids = [probe.probe_id for probe in inventory]
    required_ids = {
        "proposal-transport-contract",
        "portfolio-manifest",
        "portfolio-parity-auditor",
        "portfolio-parity-tests",
    }
    assert len(inventory) >= 52, f"red-team probe inventory below minimum: {len(inventory)}"
    assert len(probe_ids) == len(set(probe_ids)), "red-team probe IDs must be unique"
    assert required_ids.issubset(set(probe_ids)), f"missing required probes: {required_ids - set(probe_ids)}"

    result = run_campaign(tmp_path)
    assert result["probe_count"] == len(inventory), "reported probe_count must equal actual probe inventory"
    assert len(result["probes"]) == result["probe_count"]
    assert [item["probe_id"] for item in result["probes"]] == probe_ids
    failed = [item for item in result["probes"] if not item["passed"]]
    assert not failed, f"red-team probes failed: {failed}"
    assert result["passed"] is True
    assert all(item["allowed"] is False for item in result["probes"])

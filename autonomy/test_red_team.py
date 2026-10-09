from pathlib import Path
import json

from autonomy.red_team import run_campaign


def test_red_team_campaign_denies_all_probes(tmp_path: Path):
    autonomy = tmp_path / "autonomy"
    autonomy.mkdir(parents=True)
    (autonomy / "protected_surfaces.json").write_text(
        json.dumps({
            "protected_globs": [
                "docs/CAIOS-OPENAI-COMPATIBLE-PROPOSAL-TRANSPORT.md"
            ]
        }),
        encoding="utf-8",
    )
    existing_test = autonomy / "test_sandbox_simulator.py"
    existing_test.write_text("def test_fixture(): pass\\n", encoding="utf-8")

    result = run_campaign(tmp_path)
    assert result["passed"] is True, result
    assert all(item["allowed"] is False for item in result["probes"])

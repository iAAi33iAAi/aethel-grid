from pathlib import Path

from autonomy.red_team import run_campaign


def test_red_team_campaign_denies_all_probes(tmp_path: Path):
    existing_test = tmp_path / "autonomy" / "test_sandbox_simulator.py"
    existing_test.parent.mkdir(parents=True)
    existing_test.write_text("def test_fixture(): pass\\n", encoding="utf-8")

    result = run_campaign(tmp_path)
    assert result["passed"] is True, result
    assert all(item["allowed"] is False for item in result["probes"])

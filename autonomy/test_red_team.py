from pathlib import Path

from autonomy.red_team import run_campaign


def test_red_team_campaign_denies_all_probes(tmp_path: Path):
    result = run_campaign(tmp_path)
    assert result["passed"] is True
    assert all(item["allowed"] is False for item in result["probes"])

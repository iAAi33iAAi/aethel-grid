from pathlib import Path

from autonomy.system_readiness import evaluate


def test_missing_invariant_registry_is_a_blocker(tmp_path: Path):
    result = evaluate(tmp_path)
    assert result["mode"] == "HOLD"
    assert "federated-invariant-registry-missing" in result["blockers"]

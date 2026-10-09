from pathlib import Path

from autonomy.system_readiness import evaluate


def test_missing_invariant_registry_is_a_blocker(tmp_path: Path):
    result = evaluate(tmp_path)
    assert result["mode"] == "HOLD"
    assert "federated-invariant-registry-missing" in result["blockers"]

def test_runtime_readiness_is_not_claimed_without_verified_evidence(tmp_path: Path):
    result = evaluate(tmp_path)

    assert result["operational"] is False
    assert result["readiness"]["causal_runtime"] == 0.0
    assert result["readiness"]["proof_integrity"] == 0.0
    assert result["readiness"]["proof_graph"] == 0.0


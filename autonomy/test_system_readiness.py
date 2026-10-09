import json
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


def test_invalid_json_registry_is_a_blocker(tmp_path: Path):
    registry_path = tmp_path / "conformance" / "federated_invariant_registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{", encoding="utf-8")

    result = evaluate(tmp_path)

    assert result["mode"] == "HOLD"
    assert "federated-invariant-registry-invalid" in result["blockers"]


def test_malformed_registry_shapes_and_unknown_enums_fail_closed(tmp_path: Path):
    invalid_registries = [
        [],
        {"invariants": {}},
        {"invariants": [{"id": "INV-1"}]},
        {
            "invariants": [
                {
                    "id": "INV-1",
                    "domain": "test",
                    "priority": "urgent",
                    "declared_status": "partial",
                    "definition": "unknown priority must not reach scoring",
                }
            ]
        },
        {
            "invariants": [
                {
                    "id": "INV-1",
                    "domain": "test",
                    "priority": "high",
                    "declared_status": "unknown",
                    "definition": "unknown status must not be silently scored",
                }
            ]
        },
    ]

    for index, registry in enumerate(invalid_registries):
        case_root = tmp_path / str(index)
        registry_path = case_root / "conformance" / "federated_invariant_registry.json"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        result = evaluate(case_root)

        assert result["mode"] == "HOLD"
        assert "federated-invariant-registry-invalid" in result["blockers"]
        assert result["readiness"]["pfp_declared_completeness"] == 0.0


from pathlib import Path
import json

from autonomy.promotion_gate import evaluate


def test_promotion_gate_holds_without_canonical_evidence(tmp_path: Path):
    conformance = tmp_path / "conformance"
    conformance.mkdir()
    (conformance / "canonical_contract.json").write_text(json.dumps({
        "schema": "caios-conformance/v1",
        "spec_id": "SPEC-004",
        "canonical_encoding": None,
        "audit_preimage_semantics": None,
        "canonical_validator": {"path": None, "command": [], "sha256": None},
        "required_vectors": [{"id": f"TV-{i:03d}", "path": None, "sha256": None} for i in range(1, 8)],
        "promotion_policy": {"bootstrap_must_never_promote_to_canonical": True},
    }), encoding="utf-8")
    result = evaluate(tmp_path)
    assert result["decision"] == "HOLD"
    assert result["canonical"] is False

from pathlib import Path
import json

from autonomy.directive_engine import build_directives


def test_directive_engine_surfaces_canonical_and_security_work(tmp_path: Path):
    (tmp_path / "conformance").mkdir()
    (tmp_path / "conformance/canonical_contract.json").write_text(
        json.dumps({
            "schema":"caios-conformance/v1",
            "spec_id":"SPEC-004",
            "canonical_encoding":None,
            "audit_preimage_semantics":None,
            "canonical_validator":{"path":None,"command":[],"sha256":None},
            "required_vectors":[
                {"id":f"TV-{i:03d}","path":None,"sha256":None}
                for i in range(1,8)
            ],
            "promotion_policy":{"bootstrap_must_never_promote_to_canonical":True}
        }),
        encoding="utf-8",
    )
    (tmp_path / "conformance/federated_invariant_registry.json").write_text(
        json.dumps({
            "invariants":[
                {"id":"INV-007","domain":"audit","priority":"critical","declared_status":"not_implemented","definition":"signed audit"},
                {"id":"INV-013","domain":"session","priority":"critical","declared_status":"not_implemented","definition":"session anchor"},
                {"id":"INV-020","domain":"keys","priority":"high","declared_status":"not_implemented","definition":"rotation"},
            ]
        }),
        encoding="utf-8",
    )
    result = build_directives(tmp_path)
    ids = [item["directive_id"] for item in result["directives"]]
    assert "SPEC-004" in ids
    assert "INV-007" in ids
    assert "INV-013" in ids
    assert result["next_directive"] is not None

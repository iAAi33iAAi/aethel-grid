from pathlib import Path

from conformance.contract import REQUIRED_VECTOR_IDS, inspect_contract


def test_contract_is_explicitly_blocked_until_authoritative_material_exists(tmp_path: Path):
    contract = tmp_path / "conformance" / "canonical_contract.json"
    contract.parent.mkdir()
    contract.write_text(
        '{"schema":"caios-conformance/v1","spec_id":"SPEC-004","required_vectors":['
        + ",".join('{"id":"%s","path":null,"sha256":null}' % vector_id for vector_id in REQUIRED_VECTOR_IDS)
        + '],"canonical_validator":{"path":null,"command":[],"sha256":null},'
        + '"canonical_encoding":null,"audit_preimage_semantics":null}',
        encoding="utf-8",
    )
    result = inspect_contract(tmp_path)
    assert result.status == "BLOCKED"
    assert "canonical-validator.path" in result.missing
    assert "vector:TV-001:path" in result.missing


def test_contract_passes_when_validator_and_all_vectors_are_hash_anchored(tmp_path: Path):
    conformance = tmp_path / "conformance"
    vectors = conformance / "vectors"
    vectors.mkdir(parents=True)

    validator = conformance / "validator.py"
    validator.write_text("print('canonical')\n", encoding="utf-8")

    import hashlib
    import json

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    vector_defs = []
    for vector_id in REQUIRED_VECTOR_IDS:
        vector = vectors / f"{vector_id}.json"
        vector.write_text(json.dumps({"id": vector_id, "input": {}, "expected": {}}, sort_keys=True), encoding="utf-8")
        vector_defs.append({"id": vector_id, "path": str(vector.relative_to(tmp_path)), "sha256": sha(vector)})

    contract = {
        "schema": "caios-conformance/v1",
        "spec_id": "SPEC-004",
        "canonical_encoding": "declared-by-authority",
        "audit_preimage_semantics": "declared-by-authority",
        "canonical_validator": {
            "path": str(validator.relative_to(tmp_path)),
            "command": ["python", str(validator.relative_to(tmp_path))],
            "sha256": sha(validator),
        },
        "required_vectors": vector_defs,
        "promotion_policy": {"bootstrap_must_never_promote_to_canonical": True},
    }
    (conformance / "canonical_contract.json").write_text(json.dumps(contract), encoding="utf-8")

    result = inspect_contract(tmp_path)
    assert result.status == "PASS"
    assert result.missing == ()


def test_non_object_contract_root_fails_closed(tmp_path: Path):
    contract_path = tmp_path / "conformance" / "canonical_contract.json"
    contract_path.parent.mkdir()
    contract_path.write_text("[]", encoding="utf-8")

    result = inspect_contract(tmp_path)

    assert result.status == "FAIL"
    assert "contract-root-not-object" in result.warnings


def test_malformed_nested_contract_fields_fail_closed(tmp_path: Path):
    import json
    import pytest

    malformed = [
        (
            {"canonical_validator": ["not", "an", "object"]},
            "canonical-validator-not-object",
        ),
        (
            {"required_vectors": {"TV-001": "not-a-list"}},
            "required-vectors-not-list",
        ),
        (
            {"promotion_policy": ["not", "an", "object"]},
            "promotion-policy-not-object",
        ),
    ]

    for index, (patch, expected_warning) in enumerate(malformed):
        case_root = tmp_path / str(index)
        contract_path = case_root / "conformance" / "canonical_contract.json"
        contract_path.parent.mkdir(parents=True)
        contract = {
            "schema": "caios-conformance/v1",
            "spec_id": "SPEC-004",
            "canonical_validator": {"path": None, "command": [], "sha256": None},
            "required_vectors": [],
            "canonical_encoding": None,
            "audit_preimage_semantics": None,
            "promotion_policy": {},
        }
        contract.update(patch)
        contract_path.write_text(json.dumps(contract), encoding="utf-8")

        result = inspect_contract(case_root)

        assert result.status == "FAIL"
        assert expected_warning in result.warnings


def test_contract_inspection_accepts_relative_checkout_root(tmp_path: Path, monkeypatch):
    import hashlib
    import json

    root = tmp_path / "relative-repo"
    conformance = root / "conformance"
    vectors = conformance / "vectors"
    vectors.mkdir(parents=True)

    validator = conformance / "validator.py"
    validator.write_text("print('canonical')\\n", encoding="utf-8")

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    vector_defs = []
    for vector_id in REQUIRED_VECTOR_IDS:
        vector = vectors / f"{vector_id}.json"
        vector.write_text(json.dumps({"id": vector_id, "input": {}, "expected": {}}, sort_keys=True), encoding="utf-8")
        vector_defs.append({"id": vector_id, "path": str(vector.relative_to(root)), "sha256": sha(vector)})

    contract = {
        "schema": "caios-conformance/v1",
        "spec_id": "SPEC-004",
        "canonical_encoding": "declared-by-authority",
        "audit_preimage_semantics": "declared-by-authority",
        "canonical_validator": {
            "path": str(validator.relative_to(root)),
            "command": ["python", str(validator.relative_to(root))],
            "sha256": sha(validator),
        },
        "required_vectors": vector_defs,
        "promotion_policy": {"bootstrap_must_never_promote_to_canonical": True},
    }
    (conformance / "canonical_contract.json").write_text(json.dumps(contract), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    result = inspect_contract(Path("relative-repo"))

    assert result.status == "PASS"
    assert result.missing == ()


import json
from pathlib import Path

from federation.manifest_seal import ManifestSealer


def test_manifest_cli_contract_can_be_verified(tmp_path: Path):
    manifest = {"schema": "test/v1", "repositories": ["a", "b"]}
    seal = ManifestSealer.seal(manifest)
    result = ManifestSealer.verify(manifest, seal)
    assert result == (True, "verified")


def test_manifest_seal_json_round_trip():
    seal = ManifestSealer.seal({"x": 1})
    row = seal.as_dict()
    assert json.loads(json.dumps(row)) == row

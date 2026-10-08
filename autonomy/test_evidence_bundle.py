from pathlib import Path

from autonomy.evidence_bundle import build_bundle


def test_bundle_binds_artifact_hashes(tmp_path: Path):
    for relative, data in {
        "conformance/canonical_contract.json": b"contract",
        "autonomy/agent_registry.json": b"agents",
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    bundle = build_bundle(
        tmp_path,
        (
            "conformance/canonical_contract.json",
            "autonomy/agent_registry.json",
            "missing.json",
        ),
    )
    assert bundle["schema"] == "caios-evidence-bundle/v1"
    assert bundle["artifacts"][0]["status"] == "PRESENT"
    assert bundle["artifacts"][1]["status"] == "PRESENT"
    assert bundle["artifacts"][2]["status"] == "MISSING"
    assert len(bundle["bundle_digest"]) == 64

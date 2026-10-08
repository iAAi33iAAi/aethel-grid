"""
Tests for the CAIOS Federation Bridge.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
import subprocess
from pathlib import Path

from federation.caios_federation import build_federation


def test_dependency_pressure_prioritizes_missing_upstream(tmp_path: Path):
    manifest = {
        "schema": "caios-federation/v1",
        "repositories": [
            {"id": "core", "path": "core", "role": "core", "weight": 1.0, "depends_on": []},
            {"id": "consumer", "path": "consumer", "role": "consumer", "weight": 1.0, "depends_on": ["core"]},
        ],
    }
    (tmp_path / "core").mkdir()
    snapshot = build_federation(tmp_path, manifest, False)
    assert snapshot["next_inspection_target"] == "core"


def test_fingerprint_changes_when_heads_change(tmp_path: Path):
    manifest = {
        "schema": "caios-federation/v1",
        "repositories": [
            {"id": "core", "path": "core", "role": "core", "weight": 1.0, "depends_on": []}
        ],
    }
    core = tmp_path / "core"
    core.mkdir()
    first = build_federation(tmp_path, manifest, False)["system_digest"]
    (core / "README.md").write_text("x", encoding="utf-8")
    second = build_federation(tmp_path, manifest, False)["system_digest"]
    assert first != second


def test_git_untracked_content_changes_fingerprint(tmp_path: Path):
    manifest = {
        "schema": "caios-federation/v1",
        "repositories": [
            {"id": "core", "path": "core", "role": "core", "weight": 1.0, "depends_on": []}
        ],
    }
    core = tmp_path / "core"
    core.mkdir()
    subprocess.run(["git", "init"], cwd=core, check=True, capture_output=True, text=True)
    (core / "README.md").write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=core, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.name=CAIOS Test", "-c", "user.email=caios@example.invalid", "commit", "-m", "init"],
        cwd=core,
        check=True,
        capture_output=True,
        text=True,
    )
    signal = core / "signal.json"
    signal.write_text('{"value":1}\n', encoding="utf-8")
    first = build_federation(tmp_path, manifest, False)["system_digest"]
    signal.write_text('{"value":2}\n', encoding="utf-8")
    second = build_federation(tmp_path, manifest, False)["system_digest"]
    assert first != second

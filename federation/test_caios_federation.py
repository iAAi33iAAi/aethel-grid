"""
Tests for the CAIOS Federation Bridge.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
import json
import subprocess
from pathlib import Path

import pytest

from federation import caios_federation
from federation.caios_federation import build_federation, digest


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

def _committed_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("# Test repository\n", encoding="utf-8")
    (path / "LICENSE").write_text("test license\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "README.md", "LICENSE"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(
        [
            "git", "-c", "user.name=CAIOS Test", "-c", "user.email=caios@example.invalid",
            "commit", "--quiet", "-m", "initial",
        ],
        cwd=path, check=True, capture_output=True, text=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()


def _parity_manifest_and_report(workspace: Path) -> tuple[dict, dict, str]:
    revision = _committed_repo(workspace / "core")
    command = ["python", "-c", "print('verified once')"]
    scope = "Test-only verifier scope; confirms report reuse, not production conformance."
    spec = {
        "id": "core",
        "path": "core",
        "role": "core",
        "weight": 1.0,
        "depends_on": [],
        "verification": command,
        "verification_source": None,
        "verification_scope": scope,
    }
    report = {
        "schema": "caios-portfolio-ci-parity/v1",
        "generated_at_utc": "2026-10-09T20:00:00Z",
        "overall_status": "PASS",
        "summary": {
            "repositories_total": 1,
            "verified": 1,
            "not_configured": 0,
            "failed": 0,
            "passed": 1,
            "missing_or_unversioned": 0,
        },
        "repositories": [
            {
                "id": "core",
                "path": "core",
                "role": "core",
                "integration_mode": "test",
                "verification_command": command,
                "verification_source": None,
                "verification_scope": scope,
                "revision": revision,
                "status": "PASS",
                "verification": {
                    "started_at_utc": "2026-10-09T20:00:00Z",
                    "duration_seconds": 0.125,
                    "returncode": 0,
                    "stdout_tail": "verified once\n",
                    "stderr_tail": "",
                },
            }
        ],
    }
    return {"schema": "caios-federation/v1", "repositories": [spec]}, report, revision


def test_snapshot_reuses_passing_parity_report_without_rerunning_verifier(tmp_path: Path, monkeypatch):
    manifest, report, revision = _parity_manifest_and_report(tmp_path)
    real_run_argv = caios_federation.run_argv
    verifier_command = manifest["repositories"][0]["verification"]

    def reject_duplicate_verification(cwd: Path, argv: list[str], timeout: int = 120):
        if argv == verifier_command:
            pytest.fail("snapshot reran a verifier already recorded in the parity report")
        return real_run_argv(cwd, argv, timeout)

    monkeypatch.setattr(caios_federation, "run_argv", reject_duplicate_verification)
    snapshot = build_federation(tmp_path, manifest, False, verification_report=report)
    node = next(row for row in snapshot["repositories"] if row["id"] == "core")

    assert node["verification"]["status"] == "PASS"
    assert node["verification"]["audited_revision"] == revision
    assert node["verification"]["command"] == manifest["repositories"][0]["verification"]
    assert node["verification"]["verification_scope"] == manifest["repositories"][0]["verification_scope"]
    assert node["verification"]["elapsed_ms"] == 125
    assert snapshot["verification_report"]["overall_status"] == "PASS"
    assert snapshot["verification_report"]["evidence_digest"] == digest(report)
    assert node["evidence"][-1]["source"] == "portfolio-ci-parity-report"


def test_snapshot_binds_system_digest_to_parity_evidence(tmp_path: Path):
    manifest, report, _ = _parity_manifest_and_report(tmp_path)
    first = build_federation(tmp_path, manifest, False, verification_report=report)["system_digest"]
    changed_report = json.loads(json.dumps(report))
    changed_report["repositories"][0]["verification"]["stdout_tail"] = "different passing output\n"
    second = build_federation(tmp_path, manifest, False, verification_report=changed_report)["system_digest"]

    assert first != second


def test_snapshot_rejects_parity_report_command_mismatch(tmp_path: Path):
    manifest, report, _ = _parity_manifest_and_report(tmp_path)
    report["repositories"][0]["verification_command"] = ["python", "-c", "print('different')"]

    with pytest.raises(ValueError, match="command mismatch"):
        build_federation(tmp_path, manifest, False, verification_report=report)


def test_snapshot_rejects_parity_report_source_mismatch(tmp_path: Path):
    manifest, report, _ = _parity_manifest_and_report(tmp_path)
    report["repositories"][0]["verification_source"] = "https://github.com/example/core/blob/0123456789abcdef0123456789abcdef01234567/tests/test.py"

    with pytest.raises(ValueError, match="source mismatch"):
        build_federation(tmp_path, manifest, False, verification_report=report)


def test_snapshot_rejects_inconsistent_report_summary(tmp_path: Path):
    manifest, report, _ = _parity_manifest_and_report(tmp_path)
    report["summary"]["passed"] = 0

    with pytest.raises(ValueError, match="summary does not prove complete passing coverage"):
        build_federation(tmp_path, manifest, False, verification_report=report)


def test_snapshot_rejects_parity_report_revision_mismatch(tmp_path: Path):
    manifest, report, _ = _parity_manifest_and_report(tmp_path)
    report["repositories"][0]["revision"] = "0" * 40

    with pytest.raises(ValueError, match="revision mismatch"):
        build_federation(tmp_path, manifest, False, verification_report=report)


def test_snapshot_rejects_parity_report_scope_mismatch(tmp_path: Path):
    manifest, report, _ = _parity_manifest_and_report(tmp_path)
    report["repositories"][0]["verification_scope"] = "untrusted scope"

    with pytest.raises(ValueError, match="scope mismatch"):
        build_federation(tmp_path, manifest, False, verification_report=report)


def test_snapshot_rejects_nonpassing_parity_report(tmp_path: Path):
    manifest, report, _ = _parity_manifest_and_report(tmp_path)
    report["overall_status"] = "PARTIAL"

    with pytest.raises(ValueError, match="overall_status PASS"):
        build_federation(tmp_path, manifest, False, verification_report=report)


def test_snapshot_rejects_verify_and_report_modes_together(tmp_path: Path):
    manifest, report, _ = _parity_manifest_and_report(tmp_path)

    with pytest.raises(ValueError, match="mutually exclusive"):
        build_federation(tmp_path, manifest, True, verification_report=report)


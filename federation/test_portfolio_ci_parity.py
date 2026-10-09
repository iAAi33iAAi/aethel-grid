from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from federation.portfolio_ci_parity import SCHEMA, audit_portfolio


def _git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(("git", "init", "--quiet"), cwd=path, check=True, capture_output=True)
    subprocess.run(("git", "config", "user.email", "parity-test@example.invalid"), cwd=path, check=True)
    subprocess.run(("git", "config", "user.name", "Parity Test"), cwd=path, check=True)
    (path / "README.md").write_text("# parity fixture\n", encoding="utf-8")
    subprocess.run(("git", "add", "README.md"), cwd=path, check=True)
    subprocess.run(("git", "commit", "--quiet", "-m", "fixture"), cwd=path, check=True, capture_output=True)


def _manifest(path: Path, rows: list[dict]) -> Path:
    manifest = path / "federation" / "system_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"schema": "caios-federation/v1", "repositories": rows}),
        encoding="utf-8",
    )
    return manifest


def test_parity_pass_requires_every_manifest_repo_verified(tmp_path: Path):
    _git_repo(tmp_path)
    _git_repo(tmp_path / "external")
    manifest = _manifest(tmp_path, [
        {"id": "root", "path": ".", "verification": ["python", "-c", "raise SystemExit(0)"]},
        {"id": "external", "path": "external", "verification": ["python", "-c", "raise SystemExit(0)"]},
    ])

    report = audit_portfolio(root=tmp_path, manifest_path=manifest)

    assert report["schema"] == SCHEMA
    assert report["overall_status"] == "PASS"
    assert report["summary"] == {
        "repositories_total": 2,
        "verified": 2,
        "not_configured": 0,
        "failed": 0,
        "passed": 2,
        "missing_or_unversioned": 0,
    }
    assert all(len(row["revision"]) == 40 for row in report["repositories"])
    assert all(row["verification"]["returncode"] == 0 for row in report["repositories"])


def test_missing_verification_plan_is_partial_not_pass(tmp_path: Path):
    _git_repo(tmp_path)
    _git_repo(tmp_path / "unconfigured")
    manifest = _manifest(tmp_path, [
        {"id": "root", "path": ".", "verification": ["python", "-c", "raise SystemExit(0)"]},
        {"id": "unconfigured", "path": "unconfigured", "verification": []},
    ])

    report = audit_portfolio(root=tmp_path, manifest_path=manifest)

    assert report["overall_status"] == "PARTIAL"
    assert report["summary"]["verified"] == 1
    assert report["summary"]["not_configured"] == 1
    assert report["summary"]["passed"] == 1
    assert next(row for row in report["repositories"] if row["id"] == "unconfigured")["status"] == "NOT_CONFIGURED"


def test_failed_repository_command_fails_portfolio_report(tmp_path: Path):
    _git_repo(tmp_path)
    manifest = _manifest(tmp_path, [
        {"id": "root", "path": ".", "verification": ["python", "-c", "raise SystemExit(7)"]},
    ])

    report = audit_portfolio(root=tmp_path, manifest_path=manifest)

    assert report["overall_status"] == "FAILED"
    assert report["summary"]["failed"] == 1
    assert report["repositories"][0]["status"] == "FAIL"
    assert report["repositories"][0]["verification"]["returncode"] == 7


def test_manifest_rejects_path_escape(tmp_path: Path):
    _git_repo(tmp_path)
    manifest = _manifest(tmp_path, [
        {"id": "escape", "path": "../outside", "verification": ["python", "-c", "raise SystemExit(0)"]},
    ])

    with pytest.raises(ValueError, match="path escapes workspace"):
        audit_portfolio(root=tmp_path, manifest_path=manifest)


def test_manifest_rejects_duplicate_repository_identity(tmp_path: Path):
    _git_repo(tmp_path)
    manifest = _manifest(tmp_path, [
        {"id": "duplicate", "path": ".", "verification": ["python", "-c", "raise SystemExit(0)"]},
        {"id": "duplicate", "path": "other", "verification": ["python", "-c", "raise SystemExit(0)"]},
    ])

    with pytest.raises(ValueError, match="id duplicated"):
        audit_portfolio(root=tmp_path, manifest_path=manifest)


def test_missing_checkout_fails_instead_of_silently_skipping(tmp_path: Path):
    _git_repo(tmp_path)
    manifest = _manifest(tmp_path, [
        {"id": "root", "path": ".", "verification": ["python", "-c", "raise SystemExit(0)"]},
        {"id": "missing", "path": "missing", "verification": ["python", "-c", "raise SystemExit(0)"]},
    ])

    report = audit_portfolio(root=tmp_path, manifest_path=manifest)

    assert report["overall_status"] == "FAILED"
    missing = next(row for row in report["repositories"] if row["id"] == "missing")
    assert missing["status"] == "MISSING_CHECKOUT"
    assert report["summary"]["missing_or_unversioned"] == 1

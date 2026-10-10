from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from federation.portfolio_ci_parity import SCHEMA, _validate_manifest, audit_portfolio


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
    normalized_rows = []
    for row in rows:
        normalized = dict(row)
        normalized.setdefault(
            "verification_scope",
            "Test fixture scope only: exercises portfolio-auditor behavior, not repository conformance.",
        )
        normalized_rows.append(normalized)
    manifest.write_text(
        json.dumps({"schema": "caios-federation/v1", "repositories": normalized_rows}),
        encoding="utf-8",
    )
    return manifest


def test_verification_scope_is_retained_in_evidence(tmp_path: Path):
    _git_repo(tmp_path)
    scope = "Interop adapter contract only; not full repository conformance."
    manifest = _manifest(tmp_path, [
        {
            "id": "root",
            "path": ".",
            "verification": ["python", "-c", "raise SystemExit(0)"],
            "verification_source": "https://github.com/example/root/blob/0123456789abcdef0123456789abcdef01234567/tests/test_suite.py",
            "verification_scope": scope,
        },
    ])

    report = audit_portfolio(root=tmp_path, manifest_path=manifest)

    assert report["overall_status"] == "PASS"
    assert report["repositories"][0]["verification_scope"] == scope


def test_manifest_rejects_missing_verification_scope():
    with pytest.raises(ValueError, match="verification_scope must be a non-empty string"):
        _validate_manifest({
            "schema": "caios-federation/v1",
            "repositories": [
                {
                    "id": "scope-missing",
                    "path": "scope-missing",
                    "verification": ["python", "-c", "pass"],
                }
            ],
        })


def test_manifest_rejects_empty_verification_scope():
    with pytest.raises(ValueError, match="verification_scope must be a non-empty string"):
        _validate_manifest({
            "schema": "caios-federation/v1",
            "repositories": [
                {
                    "id": "bad",
                    "path": "bad",
                    "verification": ["python", "-c", "pass"],
                    "verification_scope": "  ",
                }
            ],
        })


def test_bun_is_allowlisted_for_toolchain_specific_verifiers():
    rows = _validate_manifest({
        "schema": "caios-federation/v1",
        "repositories": [
            {
                "id": "clawhub",
                "path": "clawhub",
                "verification": ["bun", "run", "ci:unit"],
                "verification_source": "https://github.com/iAAi33iAAi/clawhub/blob/5b63d5df6071a91cfd3e5e184bc44e212e977cc9/.github/workflows/ci.yml",
                "verification_scope": "ClawHub unit suite test fixture scope.",
            }
        ],
    })

    assert rows[0]["verification"] == ["bun", "run", "ci:unit"]
    assert rows[0]["verification_source"].startswith("https://")


def test_manifest_rejects_shell_as_verifier_executable():
    with pytest.raises(ValueError, match="non-allowlisted verifier executable"):
        _validate_manifest({
            "schema": "caios-federation/v1",
            "repositories": [
                {"id": "bad", "path": "bad", "verification": ["bash", "-c", "true"]}
            ],
        })


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


def test_verification_source_is_retained_in_evidence(tmp_path: Path):
    _git_repo(tmp_path)
    source = "https://github.com/example/root/blob/0123456789abcdef0123456789abcdef01234567/tests/test_suite.py"
    manifest = _manifest(tmp_path, [
        {
            "id": "root",
            "path": ".",
            "verification": ["python", "-c", "raise SystemExit(0)"],
            "verification_source": source,
        },
    ])

    report = audit_portfolio(root=tmp_path, manifest_path=manifest)

    assert report["overall_status"] == "PASS"
    assert report["repositories"][0]["verification_source"] == source


def test_manifest_rejects_non_https_verification_source(tmp_path: Path):
    _git_repo(tmp_path)
    manifest = _manifest(tmp_path, [
        {
            "id": "root",
            "path": ".",
            "verification": ["python", "-c", "raise SystemExit(0)"],
            "verification_source": "file:///tmp/untrusted-tests.py",
        },
    ])

    with pytest.raises(ValueError, match="verification_source must be an HTTPS URL"):
        audit_portfolio(root=tmp_path, manifest_path=manifest)


def test_manifest_rejects_source_for_different_repository_id():
    with pytest.raises(ValueError, match="matching the manifest repository id"):
        _validate_manifest({
            "schema": "caios-federation/v1",
            "repositories": [
                {
                    "id": "clawhub",
                    "path": "clawhub",
                    "verification": ["bun", "run", "ci:unit"],
                    "verification_source": "https://github.com/iAAi33iAAi/not-clawhub/blob/0123456789abcdef0123456789abcdef01234567/.github/workflows/ci.yml",
                }
            ],
        })


def test_manifest_rejects_mutable_verification_source(tmp_path: Path):
    _git_repo(tmp_path)
    manifest = _manifest(tmp_path, [
        {
            "id": "root",
            "path": ".",
            "verification": ["python", "-c", "raise SystemExit(0)"],
            "verification_source": "https://github.com/example/root/blob/main/tests/test_suite.py",
        },
    ])

    with pytest.raises(ValueError, match="immutable GitHub blob URL"):
        audit_portfolio(root=tmp_path, manifest_path=manifest)


def test_manifest_rejects_non_github_verification_source():
    with pytest.raises(ValueError, match="immutable GitHub blob URL"):
        _validate_manifest({
            "schema": "caios-federation/v1",
            "repositories": [
                {
                    "id": "not-github",
                    "path": "repo",
                    "verification": ["python", "-c", "pass"],
                    "verification_source": "https://example.invalid/project/blob/0123456789abcdef0123456789abcdef01234567/tests/test.py",
                }
            ],
        })


def test_gate5_ledger_matches_complete_coverage_evidence():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "federation" / "system_manifest.json").read_text(encoding="utf-8"))
    gate_status = json.loads((root / "conformance" / "GATE_STATUS.json").read_text(encoding="utf-8"))
    rows = _validate_manifest(manifest)
    gate5 = gate_status["gate_5"]
    evidence = gate5["evidence"]
    scoped = [row for row in rows if row["verification_scope"].strip()]
    sourced = [row for row in rows if row["verification_source"]]
    pinned = [row for row in sourced if re.search(r"/blob/[0-9a-f]{40}/", row["verification_source"])]
    mismatched = [
        row for row in sourced
        if urlsplit(row["verification_source"]).path.split("/")[2].casefold() != row["id"].casefold()
    ]

    assert gate5["status"] == "CLOSED"
    assert all(row["verification"] for row in rows)
    assert all(row["verification_scope"].strip() for row in rows)
    assert "verification coverage" in gate5["reason"].lower()
    assert "does not establish" in gate5["reason"].lower()
    assert "production conformance" in gate5["reason"].lower()
    assert evidence["workflow_run"] == "https://github.com/iAAi33iAAi/aethel-grid/actions/runs/38018547956"
    assert evidence["audited_commit"] == "eac6d701a08a09dc7bd4518a68df725045039e6c"
    assert evidence["status"] == "PASS"
    assert evidence["evidence_scope"] == "VERIFICATION_COVERAGE_ONLY_NOT_PRODUCTION_CONFORMANCE"
    assert evidence["repositories_total"] == len(rows) == 13
    assert evidence["verified"] == evidence["passed"] == 13
    assert evidence["not_configured"] == evidence["failed"] == 0
    assert evidence["verification_scopes_declared"] == len(scoped) == 13
    # The recorded audit predates the three additional source pins; keep its
    # counters historically accurate while validating the live manifest separately.
    assert evidence["declared_source_urls"] == evidence["pinned_source_urls"] == 10
    assert len(sourced) == len(pinned) == 13
    assert evidence["current_manifest_source_urls"] == len(sourced) == 13
    assert evidence["current_manifest_pinned_source_urls"] == len(pinned) == 13
    assert evidence["current_manifest_mutable_source_urls"] == 0
    assert evidence["current_manifest_source_repository_mismatches"] == len(mismatched) == 0
    assert evidence["mutable_source_urls"] == 0
    assert evidence["source_repository_mismatches"] == 0
    assert gate_status["gate_1"]["status"] == "BLOCKED"
    assert gate_status["gate_3"]["status"] == "PARTIALLY_CLOSED"
    assert gate_status["gate_4"]["status"] == "NOT_STARTED"
    assert gate_status["gate_6"]["status"] == "BLOCKED"


def test_every_manifest_repository_declares_explicit_verification_scope():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "federation" / "system_manifest.json").read_text(encoding="utf-8"))
    rows = _validate_manifest(manifest)

    assert len(rows) == 13
    assert all(isinstance(row["verification_scope"], str) and row["verification_scope"].strip() for row in rows)


def test_every_declared_manifest_source_is_immutable():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "federation" / "system_manifest.json").read_text(encoding="utf-8"))
    rows = _validate_manifest(manifest)
    source_rows = [row for row in rows if row["verification_source"] is not None]

    assert len(source_rows) == 13
    for row in source_rows:
        source = row["verification_source"]
        parts = urlsplit(source)
        path_parts = parts.path.split("/")
        assert parts.netloc == "github.com"
        assert path_parts[2].casefold() == row["id"].casefold()
        assert len(path_parts[4]) == 40
        assert path_parts[3] == "blob"
        assert all(ch in "0123456789abcdef" for ch in path_parts[4])


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



def test_crew_colony_verifier_is_explicitly_scoped():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "federation" / "system_manifest.json").read_text(encoding="utf-8"))
    crew = next(row for row in manifest["repositories"] if row["id"] == "crew-colony")

    assert crew["verification"] == ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
    assert crew["verification_source"] == "https://github.com/iAAi33iAAi/crew-colony/blob/4e935ab6e8d4dd3ed0e79318cf130663ec36edcd/.github/workflows/ci.yml"
    scope = crew["verification_scope"].lower()
    assert "scaffold and documentation integrity only" in scope
    assert "does not verify an executable multi-agent runtime" in scope
    assert "production conformance" in scope


def test_alexarac_verifier_is_explicitly_scoped():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "federation" / "system_manifest.json").read_text(encoding="utf-8"))
    alex = next(row for row in manifest["repositories"] if row["id"] == "ALEXARAC")

    assert alex["verification"] == ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
    assert alex["verification_source"] == "https://github.com/iAAi33iAAi/ALEXARAC/blob/457a3e0f70748f3250f447e488fe1dab1d65b827/.github/workflows/ci.yml"
    scope = alex["verification_scope"].lower()
    assert "concept-document and bill-of-materials integrity only" in scope
    assert "does not validate a deployed application" in scope
    assert "real-world performance" in scope


def test_calcula_documentation_verifier_is_explicitly_scoped():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "federation" / "system_manifest.json").read_text(encoding="utf-8"))
    calcula = next(row for row in manifest["repositories"] if row["id"] == "calcula-colony")

    assert calcula["verification"] == ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
    assert calcula["verification_source"] == "https://github.com/iAAi33iAAi/calcula-colony/blob/614b6e675ecb7a75752c9842fcc4c3e6f4179ba5/.github/workflows/ci.yml"
    scope = calcula["verification_scope"].lower()
    assert "documentation-contract verification only" in scope
    assert "does not verify a calcula engine" in scope
    assert "empirical/scientific law" in scope


def test_alpha_scaffold_verifier_is_explicitly_scoped():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "federation" / "system_manifest.json").read_text(encoding="utf-8"))
    alpha = next(row for row in manifest["repositories"] if row["id"] == "alpha-intelligence-hub")

    assert alpha["verification"] == ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
    assert alpha["verification_source"] == "https://github.com/iAAi33iAAi/alpha-intelligence-hub/blob/736c765829e3588ab6c71e57bc3dc145d9c22241/.github/workflows/ci.yml"
    assert "scaffold integrity only" in alpha["verification_scope"]
    assert "does not initialize/merge repositories" in alpha["verification_scope"]
    assert "production conformance" in alpha["verification_scope"]


def test_safety_kernel_manifest_uses_failure_aware_runner():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "federation" / "system_manifest.json").read_text(encoding="utf-8"))
    safety_kernel = next(row for row in manifest["repositories"] if row["id"] == "safety-kernel")

    # test_sk.py aggregates its check() failures and exits non-zero from main().
    # Running it under pytest would collect functions whose check() failures do
    # not raise assertions and could therefore produce a false-positive PASS.
    assert safety_kernel["verification"] == ["python", "test_sk.py"]

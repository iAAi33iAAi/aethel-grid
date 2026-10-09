#!/usr/bin/env python3
"""Run manifest-declared verification commands across checked-out federation repos.

The report is deliberately conservative:
- PASS means every manifest repository has an explicit verification command and
  every command passed at the recorded repository commit.
- PARTIAL means available checks passed but one or more repos lack verification
  commands; it is not evidence of portfolio-wide conformance.
- FAILED means a checkout, revision, command, or test failed.

Commands are invoked as argument arrays (never through a shell) with a minimal
environment and a bounded timeout. This is still normal CI execution of trusted
repository tests, not a security sandbox for hostile repository code.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

SCHEMA = "caios-portfolio-ci-parity/v1"
DEFAULT_TIMEOUT_SECONDS = 600
OUTPUT_TAIL_CHARS = 3000


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _minimal_env(home: Path, temp: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "TMPDIR": str(temp),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "CI": "true",
        "PYTHONUNBUFFERED": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }


def _git_revision(path: Path, env: dict[str, str], timeout: int) -> str | None:
    try:
        result = subprocess.run(
            ("git", "-C", str(path), "rev-parse", "HEAD"),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    revision = result.stdout.strip()
    return revision if len(revision) == 40 and all(ch in "0123456789abcdef" for ch in revision.lower()) else None


def _validate_manifest(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict) or raw.get("schema") != "caios-federation/v1":
        raise ValueError("manifest schema must be caios-federation/v1")
    rows = raw.get("repositories")
    if not isinstance(rows, list) or not rows:
        raise ValueError("manifest repositories must be a non-empty list")

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    clean: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"repository entry {index} must be an object")
        repo_id, repo_path, verification = row.get("id"), row.get("path"), row.get("verification")
        if not isinstance(repo_id, str) or not repo_id.strip():
            raise ValueError(f"repository entry {index} id must be non-empty")
        if repo_id in seen_ids:
            raise ValueError(f"repository id duplicated: {repo_id}")
        seen_ids.add(repo_id)
        if not isinstance(repo_path, str) or not repo_path.strip():
            raise ValueError(f"repository entry {index} path must be non-empty")
        candidate = Path(repo_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"repository path escapes workspace: {repo_path}")
        normalized = candidate.as_posix()
        if normalized in seen_paths:
            raise ValueError(f"repository path duplicated: {normalized}")
        seen_paths.add(normalized)
        if not isinstance(verification, list) or any(not isinstance(token, str) or not token.strip() for token in verification):
            raise ValueError(f"repository {repo_id} verification must be a list of non-empty strings")
        if verification and verification[0] not in {"python", "python3", "pytest", "cargo", "npm", "node", "go", "bun"}:
            raise ValueError(f"repository {repo_id} uses a non-allowlisted verifier executable")
        verification_source = row.get("verification_source")
        if verification_source is not None and (
            not isinstance(verification_source, str)
            or not verification_source.startswith("https://")
            or any(ch.isspace() for ch in verification_source)
        ):
            raise ValueError(f"repository {repo_id} verification_source must be an HTTPS URL")
        verification_scope = row.get("verification_scope")
        if verification_scope is not None and (
            not isinstance(verification_scope, str) or not verification_scope.strip()
        ):
            raise ValueError(f"repository {repo_id} verification_scope must be a non-empty string")
        clean.append({
            "id": repo_id,
            "path": normalized,
            "role": str(row.get("role", "unspecified")),
            "integration_mode": str(row.get("integration_mode", "unspecified")),
            "verification": list(verification),
            "verification_source": verification_source,
            "verification_scope": verification_scope,
        })
    return clean


def audit_portfolio(
    *,
    root: Path,
    manifest_path: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    manifest_path = manifest_path.resolve()
    try:
        manifest_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("manifest must be inside workspace root") from exc

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    repositories = _validate_manifest(raw)
    results: list[dict[str, Any]] = []
    run_failures = 0
    not_configured = 0
    verified = 0
    started = utc_now()

    for repo in repositories:
        repo_path = (root / repo["path"]).resolve()
        try:
            repo_path.relative_to(root)
        except ValueError:
            repo_path = root / "__invalid_path__"

        row: dict[str, Any] = {
            "id": repo["id"],
            "path": repo["path"],
            "role": repo["role"],
            "integration_mode": repo["integration_mode"],
            "verification_command": repo["verification"],
            "verification_source": repo["verification_source"],
            "verification_scope": repo["verification_scope"],
            "revision": None,
            "status": None,
            "verification": None,
        }

        if not repo_path.is_dir():
            row["status"] = "MISSING_CHECKOUT"
            row["reason"] = "manifest path is not a checked-out directory"
            run_failures += 1
            results.append(row)
            continue

        # Each command gets a temporary home and temp directory. Git checkout
        # credentials are not injected into this process environment.
        with tempfile.TemporaryDirectory(prefix="caios-parity-home-") as home_str, tempfile.TemporaryDirectory(prefix="caios-parity-tmp-") as temp_str:
            home = Path(home_str)
            temp = Path(temp_str)
            env = _minimal_env(home, temp)
            revision = _git_revision(repo_path, env, min(timeout_seconds, 30))
            row["revision"] = revision
            if revision is None:
                row["status"] = "REVISION_UNAVAILABLE"
                row["reason"] = "checkout is not a resolvable Git commit"
                run_failures += 1
                results.append(row)
                continue

            if not repo["verification"]:
                row["status"] = "NOT_CONFIGURED"
                row["reason"] = "manifest defines no verification command for this repository"
                not_configured += 1
                results.append(row)
                continue

            verified += 1
            command_started = time.monotonic()
            command_started_utc = utc_now()
            try:
                proc = subprocess.run(
                    tuple(repo["verification"]),
                    cwd=repo_path,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                    shell=False,
                )
                elapsed = round(time.monotonic() - command_started, 3)
                passed = proc.returncode == 0
                row["status"] = "PASS" if passed else "FAIL"
                row["verification"] = {
                    "started_at_utc": command_started_utc,
                    "duration_seconds": elapsed,
                    "returncode": proc.returncode,
                    "stdout_tail": proc.stdout[-OUTPUT_TAIL_CHARS:],
                    "stderr_tail": proc.stderr[-OUTPUT_TAIL_CHARS:],
                }
                if not passed:
                    run_failures += 1
            except subprocess.TimeoutExpired as exc:
                elapsed = round(time.monotonic() - command_started, 3)
                row["status"] = "TIMEOUT"
                row["verification"] = {
                    "started_at_utc": command_started_utc,
                    "duration_seconds": elapsed,
                    "timeout_seconds": timeout_seconds,
                    "stdout_tail": str(exc.stdout or "")[-OUTPUT_TAIL_CHARS:],
                    "stderr_tail": str(exc.stderr or "")[-OUTPUT_TAIL_CHARS:],
                }
                run_failures += 1
            except OSError as exc:
                row["status"] = "EXECUTION_ERROR"
                row["reason"] = f"{type(exc).__name__}: {exc}"
                run_failures += 1
            results.append(row)

    if run_failures:
        overall = "FAILED"
    elif not_configured:
        overall = "PARTIAL"
    else:
        overall = "PASS"

    summary = {
        "repositories_total": len(results),
        "verified": verified,
        "not_configured": not_configured,
        "failed": run_failures,
        "passed": sum(1 for row in results if row["status"] == "PASS"),
        "missing_or_unversioned": sum(
            1 for row in results if row["status"] in {"MISSING_CHECKOUT", "REVISION_UNAVAILABLE"}
        ),
    }
    return {
        "schema": SCHEMA,
        "generated_at_utc": started,
        "workspace_root": str(root),
        "manifest_path": str(manifest_path.relative_to(root)),
        "overall_status": overall,
        "summary": summary,
        "repositories": results,
        "interpretation": (
            "PASS requires an explicit verifier for every manifest repository and a passing result at every recorded commit. "
            "PARTIAL is not portfolio-wide conformance; repositories without a verifier remain NOT_CONFIGURED."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("federation/system_manifest.json"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("ops/caios/portfolio-ci-parity.json"))
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args()
    if args.timeout_seconds < 1 or args.timeout_seconds > 3600:
        parser.error("--timeout-seconds must be in 1..3600")

    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = audit_portfolio(
            root=root,
            manifest_path=args.manifest,
            timeout_seconds=args.timeout_seconds,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        failure = {
            "schema": SCHEMA,
            "generated_at_utc": utc_now(),
            "overall_status": "FAILED",
            "error": f"{type(exc).__name__}: {exc}",
        }
        output.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(failure, indent=2))
        return 2

    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall_status": report["overall_status"], "summary": report["summary"]}, indent=2))
    return 1 if report["overall_status"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())

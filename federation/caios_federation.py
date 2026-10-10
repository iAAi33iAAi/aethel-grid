#!/usr/bin/env python3
"""
CAIOS Federation Bridge.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi

Turns a workspace containing multiple repositories into one evidence graph.
No source is copied between repositories. The bridge only observes explicit
paths and executes verification commands declared by the trusted manifest.

The planning metric is Constitutional Dependency Pressure (CDP):

    upstream_pressure = base_gap + failure_penalty + blocked_dependents
    CDP(r) = weight(r) * upstream_pressure * (1 + dependents(r))
             -----------------------------------------------------
                        1 + verification_cost(r)

A missing/failed dependent therefore raises pressure on the dependency that
can block recovery. This makes the graph actionable instead of merely
descriptive. The metric is a coordination signal, not mutation authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def run_argv(cwd: Path, argv: list[str], timeout: int = 120) -> tuple[int, str, str]:
    if not argv:
        raise ValueError("empty verification command")
    result = subprocess.run(
        [str(x) for x in argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _safe_file_fingerprint(root: Path, max_files: int = 5000) -> str:
    """Fingerprint non-git workspaces without depending on mtime."""
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        if relative in {".DS_Store"}:
            continue
        if len(entries) >= max_files:
            entries.append({"path": "__TRUNCATED__", "count_at_limit": max_files})
            break
        try:
            data = path.read_bytes()
        except OSError as exc:
            entries.append({"path": relative, "error": type(exc).__name__})
            continue
        entries.append(
            {
                "path": relative,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return digest(entries)


def _git_worktree_fingerprint(root: Path) -> str:
    """Fingerprint a git repository including tracked HEAD and working-tree delta."""
    rc, head, _ = run_argv(root, ["git", "rev-parse", "HEAD"], timeout=15)
    if rc != 0:
        return _safe_file_fingerprint(root)

    status_rc, status, _ = run_argv(root, ["git", "status", "--porcelain=v1"], timeout=15)
    diff_rc, diff, diff_err = run_argv(root, ["git", "diff", "--binary", "HEAD"], timeout=30)
    untracked = []
    untracked_details = []
    if status_rc == 0:
        untracked = [
            line[3:] for line in status.splitlines()
            if line.startswith("?? ")
        ]
        for relative in sorted(untracked):
            path = root / relative
            try:
                data = path.read_bytes()
                untracked_details.append({
                    "path": relative,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                })
            except OSError as exc:
                untracked_details.append({
                    "path": relative,
                    "error": type(exc).__name__,
                })
    return digest(
        {
            "head": head.strip(),
            "status": status.strip() if status_rc == 0 else None,
            "diff_sha256": hashlib.sha256(diff.encode("utf-8", errors="replace")).hexdigest()
            if diff_rc == 0
            else None,
            "diff_error": diff_err[-500:] if diff_rc != 0 else None,
            "untracked": untracked_details,
        }
    )


def content_fingerprint(root: Path) -> str:
    try:
        rc, inside, _ = run_argv(root, ["git", "rev-parse", "--is-inside-work-tree"], timeout=15)
        if rc == 0 and inside.strip() == "true":
            return _git_worktree_fingerprint(root)
    except Exception:
        pass
    return _safe_file_fingerprint(root)


def index_verification_report(
    manifest: dict[str, Any], report: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Validate a passing parity report before its evidence is imported."""
    if not isinstance(report, dict) or report.get("schema") != "caios-portfolio-ci-parity/v1":
        raise ValueError("verification report has an unsupported schema")
    if report.get("overall_status") != "PASS":
        raise ValueError("verification report must have overall_status PASS")
    specs = manifest.get("repositories", [])
    if not isinstance(specs, list) or not specs:
        raise ValueError("manifest repositories must be a non-empty list")
    expected = {str(spec["id"]): spec for spec in specs}
    if len(expected) != len(specs):
        raise ValueError("manifest repository IDs must be unique")
    rows = report.get("repositories")
    if not isinstance(rows, list):
        raise ValueError("verification report repositories must be a list")

    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise ValueError("verification report has an invalid repository row")
        repo_id = row["id"]
        if repo_id in indexed:
            raise ValueError(f"verification report duplicates repository {repo_id}")
        if repo_id not in expected:
            raise ValueError(f"verification report contains unknown repository {repo_id}")
        spec = expected[repo_id]
        if row.get("path") != spec.get("path"):
            raise ValueError(f"verification report path mismatch for {repo_id}")
        if row.get("verification_command") != list(spec.get("verification", [])):
            raise ValueError(f"verification report command mismatch for {repo_id}")
        if row.get("verification_source") != spec.get("verification_source"):
            raise ValueError(f"verification report source mismatch for {repo_id}")
        if row.get("verification_scope") != spec.get("verification_scope"):
            raise ValueError(f"verification report scope mismatch for {repo_id}")
        if row.get("status") != "PASS":
            raise ValueError(f"verification report is not passing for {repo_id}")

        revision = row.get("revision")
        if (
            not isinstance(revision, str)
            or len(revision) != 40
            or any(ch not in "0123456789abcdef" for ch in revision)
        ):
            raise ValueError(f"verification report has an invalid commit revision for {repo_id}")

        verification = row.get("verification")
        if (
            not isinstance(verification, dict)
            or type(verification.get("returncode")) is not int
            or verification.get("returncode") != 0
        ):
            raise ValueError(f"verification report lacks successful command evidence for {repo_id}")
        if not isinstance(verification.get("stdout_tail", ""), str) or not isinstance(
            verification.get("stderr_tail", ""), str
        ):
            raise ValueError(f"verification report has invalid output evidence for {repo_id}")
        duration = verification.get("duration_seconds")
        if (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or not math.isfinite(float(duration))
            or duration < 0
        ):
            raise ValueError(f"verification report has invalid duration for {repo_id}")
        indexed[repo_id] = row

    if set(indexed) != set(expected):
        missing = sorted(set(expected) - set(indexed))
        raise ValueError(f"verification report does not cover every manifest repository: {missing}")

    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("verification report summary is missing")
    required_summary = {
        "repositories_total": len(expected),
        "verified": len(expected),
        "passed": len(expected),
        "not_configured": 0,
        "failed": 0,
    }
    for field, expected_value in required_summary.items():
        actual_value = summary.get(field)
        if type(actual_value) is not int or actual_value != expected_value:
            raise ValueError(
                "verification report summary does not prove complete passing coverage: "
                f"{field}={actual_value!r}, expected={expected_value}"
            )
    generated_at = report.get("generated_at_utc")
    if not isinstance(generated_at, str) or not generated_at.strip():
        raise ValueError("verification report timestamp is missing")
    return indexed


def repo_snapshot(
    workspace: Path,
    spec: dict[str, Any],
    run_verification: bool,
    verification_report_entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = (workspace / str(spec["path"])).resolve()
    if not root.is_dir():
        if verification_report_entry is not None:
            raise ValueError(f"verification report references missing checkout for {spec['id']}")
        return {
            "id": spec["id"],
            "role": spec.get("role", ""),
            "status": "MISSING",
            "path": str(spec["path"]),
            "weight": float(spec.get("weight", 1.0)),
            "depends_on": list(spec.get("depends_on", [])),
            "verification": None,
            "metadata": {"has_readme": False, "has_license": False, "dirty": False},
            "evidence": [],
            "content_fingerprint": digest("missing"),
        }

    evidence: list[dict[str, Any]] = []

    def probe(argv: list[str], kind: str) -> str | None:
        try:
            rc, out, err = run_argv(root, argv, timeout=30)
        except Exception as exc:
            evidence.append({
                "kind": kind,
                "status": "FAIL",
                "details": {"exception": type(exc).__name__, "message": str(exc)},
            })
            return None
        evidence.append({
            "kind": kind,
            "status": "PASS" if rc == 0 else "FAIL",
            "details": {
                "returncode": rc,
                "stdout": out.strip()[-4000:],
                "stderr": err.strip()[-2000:],
            },
        })
        return out.strip() if rc == 0 else None

    head = probe(["git", "rev-parse", "HEAD"], "head")
    branch = probe(["git", "branch", "--show-current"], "branch")
    status = probe(["git", "status", "--porcelain"], "working-tree")
    remote = probe(["git", "remote", "get-url", "origin"], "origin")
    latest = probe(["git", "log", "-1", "--format=%cI"], "latest-commit")

    has_readme = any((root / n).is_file() for n in ("README.md", "README.rst", "README.txt"))
    has_license = any((root / n).is_file() for n in ("LICENSE", "LICENSE.md", "COPYING"))
    metadata = {
        "has_readme": has_readme,
        "has_license": has_license,
        "head": head,
        "branch": branch,
        "dirty": bool(status),
        "origin": remote,
        "latest_commit": latest,
    }
    evidence.append({
        "kind": "repository-metadata",
        "status": "PASS" if has_readme and has_license else "FAIL",
        "details": metadata,
    })

    verification = None
    if verification_report_entry is not None:
        audited_revision = verification_report_entry["revision"]
        if metadata.get("head") != audited_revision:
            raise ValueError(
                f"verification report revision mismatch for {spec['id']}: "
                f"current={metadata.get('head')!r}, audited={audited_revision!r}"
            )
        report_verification = verification_report_entry["verification"]
        verification = {
            "status": verification_report_entry["status"],
            "returncode": report_verification["returncode"],
            "command": list(spec["verification"]),
            "stdout_tail": report_verification.get("stdout_tail", "")[-5000:],
            "stderr_tail": report_verification.get("stderr_tail", "")[-3000:],
            "elapsed_ms": round(float(report_verification["duration_seconds"]) * 1000),
            "started_at_utc": report_verification.get("started_at_utc"),
            "audited_revision": audited_revision,
            "verification_source": spec.get("verification_source"),
            "verification_scope": spec["verification_scope"],
            "audit_row_digest": digest(verification_report_entry),
        }
        evidence.append({"kind": "verification", "source": "portfolio-ci-parity-report", **verification})
    elif run_verification and spec.get("verification"):
        started = time.monotonic_ns()
        rc, out, err = run_argv(root, list(spec["verification"]), timeout=180)
        verification = {
            "status": "PASS" if rc == 0 else "FAIL",
            "returncode": rc,
            "command": list(spec["verification"]),
            "stdout_tail": out[-5000:],
            "stderr_tail": err[-3000:],
            "elapsed_ms": (time.monotonic_ns() - started) // 1_000_000,
        }
        evidence.append({"kind": "verification", **verification})

    return {
        "id": spec["id"],
        "role": spec.get("role", ""),
        "status": "PRESENT",
        "path": str(spec["path"]),
        "weight": float(spec.get("weight", 1.0)),
        "depends_on": list(spec.get("depends_on", [])),
        "metadata": metadata,
        "verification": verification,
        "content_fingerprint": content_fingerprint(root),
        "evidence": evidence,
    }


def dependency_pressure(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dependents = {n["id"]: 0 for n in nodes}
    blocked_dependents = {n["id"]: 0 for n in nodes}

    for node in nodes:
        failed = node["status"] != "PRESENT" or bool(
            node.get("verification")
            and node["verification"].get("status") == "FAIL"
        )
        for dep in node.get("depends_on", []):
            if dep in dependents:
                dependents[dep] += 1
                if failed:
                    blocked_dependents[dep] += 1

    ranked = []
    for node in nodes:
        missing = node["status"] != "PRESENT"
        failed = missing or bool(
            node.get("verification")
            and node["verification"].get("status") == "FAIL"
        )
        evidence_gap = 1.0 if missing else 0.0
        if node["status"] == "PRESENT" and not node["metadata"].get("has_license"):
            evidence_gap += 0.5

        cost = 0.0 if not node.get("verification") else max(
            0.0, node["verification"].get("elapsed_ms", 1) / 1000.0
        )

        upstream_pressure = (
            evidence_gap
            + 2.0 * float(failed)
            + 1.5 * float(blocked_dependents[node["id"]])
        )
        cdp = (
            float(node.get("weight", 1.0))
            * upstream_pressure
            * (1 + dependents[node["id"]])
            / (1 + cost)
        )
        ranked.append(
            {
                **node,
                "dependents": dependents[node["id"]],
                "blocked_dependents": blocked_dependents[node["id"]],
                "constitutional_dependency_pressure": round(cdp, 6),
            }
        )
    ranked.sort(
        key=lambda x: (
            x["constitutional_dependency_pressure"],
            x["blocked_dependents"],
            x["dependents"],
            x["id"],
        ),
        reverse=True,
    )
    return ranked


def build_federation(
    workspace: Path,
    manifest: dict[str, Any],
    run_verification: bool,
    verification_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if run_verification and verification_report is not None:
        raise ValueError("--verify and --verification-report are mutually exclusive")
    report_index = index_verification_report(manifest, verification_report) if verification_report is not None else None
    nodes = [
        repo_snapshot(
            workspace,
            spec,
            run_verification,
            report_index.get(str(spec["id"])) if report_index is not None else None,
        )
        for spec in manifest.get("repositories", [])
    ]
    ranked = dependency_pressure(nodes)
    system_digest = digest(
        {
            "schema": manifest.get("schema"),
            "verification_report_digest": (
                digest(verification_report) if verification_report is not None else None
            ),
            "nodes": [
                {
                    "id": n["id"],
                    "status": n["status"],
                    "head": n.get("metadata", {}).get("head"),
                    "content_fingerprint": n.get("content_fingerprint"),
                    "verification": (n.get("verification") or {}).get("status"),
                    "verification_evidence_digest": (
                        digest(n["verification"]) if n.get("verification") is not None else None
                    ),
                    "cdp": n["constitutional_dependency_pressure"],
                }
                for n in ranked
            ],
        }
    )
    return {
        "schema": manifest.get("schema", "caios-federation/v1"),
        "generated_at_unix": time.time(),
        "system_digest": system_digest,
        "next_inspection_target": ranked[0]["id"] if ranked else None,
        "verification_report": (
            {
                "schema": verification_report.get("schema"),
                "overall_status": verification_report.get("overall_status"),
                "generated_at_utc": verification_report.get("generated_at_utc"),
                "summary": verification_report.get("summary"),
                "evidence_digest": digest(verification_report),
            }
            if verification_report is not None
            else None
        ),
        "repositories": ranked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAIOS federation bridge")
    parser.add_argument("--manifest", default="federation/system_manifest.json")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--verify", action="store_true", help="Run manifest verifiers directly.")
    parser.add_argument(
        "--verification-report",
        type=Path,
        help="Reuse a passing caios-portfolio-ci-parity/v1 JSON report instead of rerunning verifiers.",
    )
    parser.add_argument("--output", default="ops/caios/federation-snapshot.json")
    args = parser.parse_args(argv)
    if args.verify and args.verification_report is not None:
        parser.error("--verify and --verification-report are mutually exclusive")

    try:
        workspace = Path(args.workspace).resolve()
        manifest = json.loads((workspace / args.manifest).read_text(encoding="utf-8"))
        verification_report = None
        if args.verification_report is not None:
            report_path = args.verification_report
            if not report_path.is_absolute():
                report_path = workspace / report_path
            verification_report = json.loads(report_path.read_text(encoding="utf-8"))
        snapshot = build_federation(
            workspace,
            manifest,
            args.verify,
            verification_report=verification_report,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 2

    output = workspace / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

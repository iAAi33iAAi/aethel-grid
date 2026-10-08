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
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
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


def repo_snapshot(workspace: Path, spec: dict[str, Any], run_verification: bool) -> dict[str, Any]:
    root = (workspace / str(spec["path"])).resolve()
    if not root.is_dir():
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
    if run_verification and spec.get("verification"):
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


def build_federation(workspace: Path, manifest: dict[str, Any], run_verification: bool) -> dict[str, Any]:
    nodes = [
        repo_snapshot(workspace, spec, run_verification)
        for spec in manifest.get("repositories", [])
    ]
    ranked = dependency_pressure(nodes)
    system_digest = digest(
        {
            "schema": manifest.get("schema"),
            "nodes": [
                {
                    "id": n["id"],
                    "status": n["status"],
                    "head": n.get("metadata", {}).get("head"),
                    "content_fingerprint": n.get("content_fingerprint"),
                    "verification": (n.get("verification") or {}).get("status"),
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
        "repositories": ranked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAIOS federation bridge")
    parser.add_argument("--manifest", default="federation/system_manifest.json")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", default="ops/caios/federation-snapshot.json")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    manifest = json.loads((workspace / args.manifest).read_text(encoding="utf-8"))
    snapshot = build_federation(workspace, manifest, args.verify)
    output = workspace / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

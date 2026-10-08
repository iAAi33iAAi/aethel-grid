#!/usr/bin/env python3
"""
CAIOS Federation Bridge.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi

Turns a workspace containing multiple repositories into one evidence graph.
No source is copied between repositories. The bridge only observes explicit
paths and executes verification commands declared by the trusted manifest.

The planning metric is Constitutional Dependency Pressure (CDP):

    CDP(r) = weight(r) * (gap(r) + 2 * failure(r)) * (1 + dependents(r))
             ----------------------------------------------------------------
                               1 + verification_cost(r)

The repository with the highest CDP is the preferred next inspection target.
This is a coordination metric, not a permission to mutate code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


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


def repo_snapshot(workspace: Path, spec: dict[str, Any], run_verification: bool) -> dict[str, Any]:
    root = (workspace / str(spec["path"])).resolve()
    if not root.is_dir():
        return {
            "id": spec["id"],
            "role": spec.get("role", ""),
            "status": "MISSING",
            "path": str(spec["path"]),
            "evidence": [],
        }

    evidence: list[dict[str, Any]] = []

    def probe(argv: list[str], kind: str) -> str | None:
        try:
            rc, out, err = run_argv(root, argv, timeout=30)
        except Exception as exc:
            evidence.append({"kind": kind, "status": "FAIL", "details": {"exception": type(exc).__name__, "message": str(exc)}})
            return None
        evidence.append({
            "kind": kind,
            "status": "PASS" if rc == 0 else "FAIL",
            "details": {"returncode": rc, "stdout": out.strip()[-4000:], "stderr": err.strip()[-2000:]},
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
        "evidence": evidence,
    }


def dependency_pressure(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {n["id"]: n for n in nodes}
    dependents = {n["id"]: 0 for n in nodes}
    for node in nodes:
        for dep in node.get("depends_on", []):
            if dep in dependents:
                dependents[dep] += 1

    ranked = []
    for node in nodes:
        missing = node["status"] != "PRESENT"
        failed = missing or bool(node.get("verification") and node["verification"].get("status") == "FAIL")
        evidence_gap = 1.0 if missing else 0.0
        if node["status"] == "PRESENT" and not node["metadata"].get("has_license"):
            evidence_gap += 0.5
        cost = 1.0 if not node.get("verification") else max(1.0, node["verification"].get("elapsed_ms", 1) / 1000.0)
        cdp = float(node.get("weight", 1.0)) * (evidence_gap + 2.0 * float(failed)) * (1 + dependents[node["id"]]) / (1 + cost)
        ranked.append({**node, "dependents": dependents[node["id"]], "constitutional_dependency_pressure": round(cdp, 6)})
    ranked.sort(key=lambda x: x["constitutional_dependency_pressure"], reverse=True)
    return ranked


def build_federation(workspace: Path, manifest: dict[str, Any], run_verification: bool) -> dict[str, Any]:
    nodes = [
        repo_snapshot(workspace, spec, run_verification)
        for spec in manifest.get("repositories", [])
    ]
    ranked = dependency_pressure(nodes)
    system_digest = digest({
        "schema": manifest.get("schema"),
        "nodes": [
            {
                "id": n["id"],
                "status": n["status"],
                "head": n.get("metadata", {}).get("head"),
                "verification": (n.get("verification") or {}).get("status"),
                "cdp": n["constitutional_dependency_pressure"],
            }
            for n in ranked
        ],
    })
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

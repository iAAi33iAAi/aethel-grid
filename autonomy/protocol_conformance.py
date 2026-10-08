#!/usr/bin/env python3
"""
CAIOS protocol conformance planner/runner.

Only registry-declared commands may execute. The runner reports unavailable
conformance tooling as NOT_CONFIGURED instead of treating absence as success.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autonomy.evidence_bundle import digest
from autonomy.protocol_admission import ProtocolRegistry


@dataclass(frozen=True)
class ConformanceResult:
    protocol: str
    expected_revision: str
    status: str
    command: tuple[str, ...]
    returncode: int | None
    stdout_tail: str
    stderr_tail: str
    evidence_digest: str


class ProtocolConformanceRunner:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.registry = ProtocolRegistry(self.repo_root)

    def available_command(self, protocol_id: str) -> tuple[str, ...] | None:
        profile = self.registry.get(protocol_id)
        if profile is None:
            return None
        candidates = {
            "acp": ("acp-tck",),
            "a2a": ("a2a", "version"),
            "mcp": ("mcp", "--help"),
        }
        command = candidates.get(protocol_id)
        if not command or not shutil.which(command[0]):
            return None
        return command

    def plan(self) -> list[dict[str, Any]]:
        rows = []
        for protocol_id, profile in sorted(self.registry.protocols.items()):
            command = self.available_command(protocol_id)
            rows.append({
                "protocol": protocol_id,
                "revision": profile.version,
                "status": profile.status,
                "command": list(command) if command else None,
                "conformance": "CONFIGURED" if command else "NOT_CONFIGURED",
                "source_url": profile.source_url,
            })
        return rows

    def run(self, protocol_id: str) -> ConformanceResult:
        profile = self.registry.get(protocol_id)
        if profile is None:
            return ConformanceResult(
                protocol=protocol_id,
                expected_revision="unknown",
                status="REJECTED",
                command=(),
                returncode=None,
                stdout_tail="",
                stderr_tail="protocol-not-registered",
                evidence_digest=digest("protocol-not-registered"),
            )

        command = self.available_command(protocol_id)
        if command is None:
            material = {
                "protocol": protocol_id,
                "revision": profile.version,
                "status": "NOT_CONFIGURED",
            }
            return ConformanceResult(
                protocol=protocol_id,
                expected_revision=profile.version,
                status="NOT_CONFIGURED",
                command=(),
                returncode=None,
                stdout_tail="",
                stderr_tail="",
                evidence_digest=digest(material),
            )

        import subprocess

        proc = subprocess.run(
            command,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        material = {
            "protocol": protocol_id,
            "revision": profile.version,
            "command": list(command),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
        return ConformanceResult(
            protocol=protocol_id,
            expected_revision=profile.version,
            status="PASS" if proc.returncode == 0 else "FAIL",
            command=command,
            returncode=proc.returncode,
            stdout_tail=proc.stdout[-4000:],
            stderr_tail=proc.stderr[-4000:],
            evidence_digest=digest(material),
        )


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="CAIOS protocol conformance planner")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--protocol")
    parser.add_argument("--output", default="ops/caios/protocol-conformance.json")
    args = parser.parse_args(argv)

    runner = ProtocolConformanceRunner(Path(args.repo_root))
    if args.plan or not args.protocol:
        result: dict[str, Any] = {
            "schema": "caios-protocol-conformance/v1",
            "mode": "PLAN",
            "protocols": runner.plan(),
        }
    else:
        item = runner.run(args.protocol)
        result = {
            "schema": "caios-protocol-conformance/v1",
            "mode": "RUN",
            "result": item.__dict__,
        }

    output = runner.repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

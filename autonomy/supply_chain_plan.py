#!/usr/bin/env python3
"""
CAIOS supply-chain evidence planner.

Builds a deterministic evidence plan for SLSA provenance, SBOM generation,
vulnerability scanning, repository security health, policy evaluation,
provenance attestation, telemetry, and release signing.

The planner does not install or trust tools. Exact tool commands are admitted
only through integrations/caios_tool_registry.json.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autonomy.evidence_bundle import digest
from integrations.tool_registry import ToolRegistry


@dataclass(frozen=True)
class SupplyChainCheck:
    check_id: str
    objective: str
    standard: str
    tool_id: str
    required: bool
    available: bool
    authority: str
    license: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "objective": self.objective,
            "standard": self.standard,
            "tool_id": self.tool_id,
            "required": self.required,
            "available": self.available,
            "authority": self.authority,
            "license": self.license,
        }


CHECKS = (
    ("slsa-provenance", "Bind release artifact to source and build provenance.", "SLSA 1.2", "cosign", True),
    ("sbom", "Generate machine-readable SBOM for release material.", "SPDX/CycloneDX", "syft", True),
    ("vulnerability", "Scan release material for known vulnerabilities.", "Grype", "grype", True),
    ("repository-security", "Measure repository supply-chain security posture.", "OpenSSF Scorecard", "scorecard", False),
    ("policy", "Evaluate declared policy bundles deterministically.", "OPA/Rego", "opa", False),
    ("provenance", "Bind artifacts to build attestations.", "in-toto/DSSE", "in-toto", True),
    ("telemetry", "Emit stable CI/CD and agent lifecycle telemetry.", "OpenTelemetry", "otel", False),
    ("artifact-signing", "Verify release signatures and attestations.", "Sigstore/Cosign", "cosign", True),
)


def build_plan(repo_root: Path) -> dict[str, Any]:
    registry = ToolRegistry(repo_root)
    checks = []

    for check_id, objective, standard, tool_id, required in CHECKS:
        spec = registry.get(tool_id)
        available = bool(spec and spec.executable)
        authority = spec.authority if spec else "unknown"
        license_name = spec.license if spec else "unknown"
        checks.append(
            SupplyChainCheck(
                check_id=check_id,
                objective=objective,
                standard=standard,
                tool_id=tool_id,
                required=required,
                available=available,
                authority=authority,
                license=license_name,
            )
        )

    blockers = [
        check.check_id
        for check in checks
        if check.required and not check.available
    ]
    material = {
        "schema": "caios-supply-chain-plan/v1",
        "checks": [check.as_dict() for check in checks],
        "blockers": blockers,
        "routine_ci_attestation_policy": "do-not-attest-routine-test-builds",
        "release_attestation_policy": "attest-release-bundles-only",
        "standards": {
            "slsa": "1.2",
            "attestation": "in-toto/DSSE",
            "signature": "Sigstore/Cosign",
        },
    }
    return {
        **material,
        "plan_digest": digest(material),
    }


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="build CAIOS supply-chain evidence plan")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="ops/caios/supply-chain-plan.json")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    result = build_plan(root)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
CAIOS deterministic evidence bundle.

A bundle is an inventory of the artifacts that describe one autonomous
decision surface. It records content hashes, not authority. Optional signing
belongs outside this module (for example through a configured Sigstore/Cosign
adapter).

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_ARTIFACTS = (
    "conformance/canonical_contract.json",
    "federation/system_manifest.json",
    "autonomy/agent_registry.json",
    "integrations/caios_tool_registry.json",
    "autonomy/model_registry.json",
    "autonomy/authority_lattice.json",
    "THIRD_PARTY_AUTONOMY_NOTICES.md",
    "ops/caios/autonomy-certificates.jsonl",
    "ops/caios/session-anchors.jsonl",
    "ops/caios/evidence-ledger.jsonl",
    "ops/caios/telemetry.jsonl",
    "ops/caios/slsa-provenance.json",
    "ops/caios/federation-manifest-seal.json",
    "ops/caios/proof-graph.json",
    "ops/caios/agent-reputation.jsonl",
)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def build_bundle(repo_root: Path, artifacts: tuple[str, ...] = DEFAULT_ARTIFACTS) -> dict[str, Any]:
    entries = []
    for relative in artifacts:
        path = (repo_root / relative).resolve()
        try:
            path.relative_to(repo_root)
        except ValueError:
            entries.append({"path": relative, "status": "INVALID_PATH"})
            continue
        if not path.is_file():
            entries.append({"path": relative, "status": "MISSING"})
            continue
        entries.append({
            "path": relative,
            "status": "PRESENT",
            "size": path.stat().st_size,
            "sha256": file_sha256(path),
        })

    material = {
        "schema": "caios-evidence-bundle/v1",
        "artifacts": entries,
    }
    return {
        **material,
        "bundle_digest": digest(material),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="build CAIOS evidence bundle")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="ops/caios/evidence-bundle.json")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    bundle = build_bundle(root)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

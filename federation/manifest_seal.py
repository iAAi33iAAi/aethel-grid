#!/usr/bin/env python3
"""
Generate and verify a CAIOS federation manifest seal.

The default seal is unsigned but cryptographically binds the exact manifest
contents. Production deployments may supply an Ed25519 identity and private
key through a separate secret-management adapter.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from federation.security_primitives import ManifestSeal, ManifestSealer


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="seal CAIOS federation manifest")
    parser.add_argument(
        "--manifest",
        default="federation/system_manifest.json",
    )
    parser.add_argument(
        "--output",
        default="ops/caios/federation-manifest-seal.json",
    )
    args = parser.parse_args()

    root = Path(".").resolve()
    manifest_path = (root / args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    seal = ManifestSealer.seal(manifest)

    result = {
        "schema": "caios-federation-manifest-seal/v1",
        "manifest": args.manifest,
        "seal": seal.as_dict(),
    }
    result["verification"] = ManifestSealer.verify(manifest, seal)[1]

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

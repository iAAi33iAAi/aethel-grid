#!/usr/bin/env python3
"""
CAIOS SLSA v1 provenance predicate builder.

This module constructs an unsigned provenance predicate from local repository
and CI metadata. It does not claim SLSA conformance by itself; a trusted
attestation service must sign and publish the resulting predicate.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PREDICATE_TYPE = "https://slsa.dev/provenance/v1"
BUILD_TYPE = "https://github.com/iAAi33iAAi/aethel-grid/caios-build/v1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_value(repo_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ("git", *args),
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def build_provenance(
    repo_root: Path,
    subjects: tuple[str, ...] = (),
) -> dict[str, Any]:
    root = repo_root.resolve()
    started = datetime.now(timezone.utc).isoformat()

    subject_rows = []
    for relative in subjects:
        path = root / relative
        if path.is_file():
            subject_rows.append({
                "name": relative,
                "digest": {"sha256": sha256(path)},
            })

    invocation_id = (
        os.getenv("GITHUB_RUN_ID")
        or f"local-{git_value(root, 'rev-parse', 'HEAD') or 'unknown'}"
    )
    commit = git_value(root, "rev-parse", "HEAD")

    predicate = {
        "buildDefinition": {
            "buildType": BUILD_TYPE,
            "externalParameters": {
                "repository": os.getenv("GITHUB_REPOSITORY", "iAAi33iAAi/aethel-grid"),
                "ref": os.getenv("GITHUB_REF", "local"),
                "sha": commit,
            },
            "internalParameters": {
                "python": platform.python_version(),
                "system": platform.system(),
                "machine": platform.machine(),
            },
            "resolvedDependencies": [
                {
                    "uri": f"git+https://github.com/iAAi33iAAi/aethel-grid@{commit}",
                    "digest": {"gitCommit": commit},
                }
            ] if commit else [],
        },
        "runDetails": {
            "builder": {
                "id": os.getenv(
                    "GITHUB_ACTIONS",
                    "local-caios-builder",
                )
            },
            "metadata": {
                "invocationId": invocation_id,
                "startedOn": started,
            },
        },
    }

    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subject_rows,
        "predicateType": PREDICATE_TYPE,
        "predicate": predicate,
    }


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="build unsigned SLSA v1 provenance predicate")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--subject", action="append", default=[])
    parser.add_argument("--output", default="ops/caios/slsa-provenance.json")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    document = build_provenance(root, tuple(args.subject))
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

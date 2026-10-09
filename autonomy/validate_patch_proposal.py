#!/usr/bin/env python3
"""
CAIOS isolated patch verifier.

Consumes a proposal artifact, checks it against the current trusted base,
revalidates registry attestation and the constitutional gate, then tests it in
a standalone clone using a Bubblewrap network socket egress filter. The runner home and
host temporary credential paths are hidden and toolchain paths are read-only.
This job must not receive model API keys or a repository write token.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from autonomy.patch_proposal import SCHEMA, select_candidate
from autonomy.sandbox_simulator import DisposableWorktree
from autonomy.caios_runtime import digest

VALIDATION_COMMAND = (
    "bash",
    "-e",
    "-u",
    "-o",
    "pipefail",
    "-c",
    (
        "python -m pytest -q autonomy conformance federation interop && "
        "rustc --test conformance/test_gate3_reference.rs -o /tmp/caios-gate3-tests && "
        "/tmp/caios-gate3-tests && "
        "node --experimental-strip-types conformance/gate3_reference_test.ts && "
        "python3 specs/spec-004/validate_spec_004.py"
    ),
)


def current_head(repo_root: Path) -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"cannot-read-current-head:{result.stderr[-1000:]}")
    return result.stdout.strip()


def validate_artifact(
    repo_root: Path,
    artifact: dict[str, Any],
    *,
    head_sha: str | None = None,
    max_risk: float = 0.55,
) -> dict[str, Any]:
    if not isinstance(artifact, dict) or artifact.get("schema") != SCHEMA:
        return {"status": "REJECTED", "reason": "proposal-schema-invalid"}
    if artifact.get("status") != "PROPOSED":
        return {"status": "NO_CANDIDATE", "reason": "proposal-artifact-is-not-proposed"}

    observed_head = head_sha or current_head(repo_root)
    base_sha = artifact.get("base_sha")
    if not isinstance(base_sha, str) or base_sha != observed_head:
        return {
            "status": "STALE",
            "reason": "proposal-base-does-not-match-validation-checkout",
            "expected_base_sha": base_sha,
            "observed_base_sha": observed_head,
        }

    proposal = artifact.get("source_proposal")
    if not isinstance(proposal, dict):
        return {"status": "REJECTED", "reason": "source-proposal-missing"}
    expected_digest = digest(proposal)
    if expected_digest != artifact.get("proposal_digest"):
        return {"status": "REJECTED", "reason": "source-proposal-digest-mismatch"}

    revalidated = select_candidate(
        repo_root,
        observed_head,
        [proposal],
        max_risk=max_risk,
        max_proposals=1,
    )
    if revalidated.get("status") != "PROPOSED":
        return {
            "status": "REJECTED",
            "reason": "proposal-failed-independent-gate-revalidation",
            "revalidation": revalidated,
        }
    if revalidated.get("proposal_digest") != expected_digest:
        return {"status": "REJECTED", "reason": "revalidated-proposal-digest-mismatch"}
    return {
        "status": "READY_FOR_TEST",
        "base_sha": observed_head,
        "proposal_digest": expected_digest,
        "candidate": revalidated,
    }


def validate_and_test(
    repo_root: Path,
    input_path: Path,
    output_path: Path,
    *,
    max_risk: float = 0.55,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    model_key_names = sorted(
        name for name, value in os.environ.items()
        if name.startswith("CAIOS_") and name.endswith("_API_KEY") and value
    )
    write_token_names = sorted(
        name for name in ("CAIOS_AUTOBUILD_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
        if os.environ.get(name)
    )
    if model_key_names or write_token_names:
        result = {
            "schema": "caios-patch-validation/v1",
            "status": "BLOCKED",
            "reason": "validation-job-credential-isolation-violated",
            "model_api_key_environment_names": model_key_names,
            "write_token_environment_names": write_token_names,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result
    artifact = json.loads(input_path.read_text(encoding="utf-8"))
    preflight = validate_artifact(repo_root, artifact, max_risk=max_risk)
    if preflight.get("status") != "READY_FOR_TEST":
        result = {
            "schema": "caios-patch-validation/v1",
            **preflight,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    candidate = preflight["candidate"]
    patch = candidate.get("unified_diff")
    if not isinstance(patch, str) or not patch:
        result = {
            "schema": "caios-patch-validation/v1",
            "status": "REJECTED",
            "reason": "revalidated-patch-missing",
        }
    else:
        simulation = DisposableWorktree(repo_root).run(
            patch,
            VALIDATION_COMMAND,
            require_egress_block=True,
        )
        result = {
            "schema": "caios-patch-validation/v1",
            "status": "VALIDATED" if simulation.status == "PASS" and simulation.egress_blocked else "VALIDATION_FAILED",
            "base_sha": preflight["base_sha"],
            "proposal_digest": preflight["proposal_digest"],
            "patch_digest": digest(patch),
            "candidate": candidate,
            "sandbox_evidence": simulation.as_dict(),
            "validation_contract": {
                "runs_in_disposable_standalone_clone": True,
                "egress_block_required": True,
                "egress_block_established": simulation.egress_blocked,
                "sandbox_mode": "bubblewrap-seccomp-socket-deny" if simulation.egress_blocked else "failed-closed",
                "model_api_keys_present": bool(model_key_names),
                "repository_write_token_present": bool(write_token_names),
                "fixed_validation_command": list(VALIDATION_COMMAND),
            },
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="revalidate and test one CAIOS patch proposal")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="/tmp/caios-patch-validation.json")
    parser.add_argument("--max-risk", type=float, default=0.55)
    args = parser.parse_args(argv)

    try:
        result = validate_and_test(
            Path(args.repo_root),
            Path(args.input),
            Path(args.output),
            max_risk=args.max_risk,
        )
    except Exception as exc:
        result = {
            "schema": "caios-patch-validation/v1",
            "status": "BLOCKED",
            "reason": f"{type(exc).__name__}:{str(exc)[:1000]}",
        }
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "VALIDATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

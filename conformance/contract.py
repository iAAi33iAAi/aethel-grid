#!/usr/bin/env python3
"""
CAIOS canonical-conformance contract inspector.

This module deliberately does not invent SPEC-004 semantics. It defines the
evidence required before a repository can claim canonical conformance.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_VECTOR_IDS = tuple(f"TV-{index:03d}" for index in range(1, 8))


@dataclass(frozen=True)
class ContractResult:
    status: str
    spec_id: str
    contract_digest: str
    missing: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "spec_id": self.spec_id,
            "contract_digest": self.contract_digest,
            "missing": list(self.missing),
            "warnings": list(self.warnings),
            "evidence": self.evidence,
        }


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_contract(repo_root: Path, contract_path: str = "conformance/canonical_contract.json") -> ContractResult:
    # Normalize once so containment checks work for both absolute and relative
    # checkout paths supplied by callers.
    repo_root = repo_root.resolve()
    path = (repo_root / contract_path).resolve()
    if not path.is_file():
        return ContractResult(
            status="BLOCKED",
            spec_id="SPEC-004",
            contract_digest=digest("missing-contract"),
            missing=("contract-file",),
            warnings=(),
            evidence={"path": contract_path},
        )

    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ContractResult(
            status="FAIL",
            spec_id="SPEC-004",
            contract_digest=digest({"error": str(exc)}),
            missing=(),
            warnings=(f"cannot-read-contract:{type(exc).__name__}",),
            evidence={},
        )

    if not isinstance(contract, dict):
        return ContractResult(
            status="FAIL",
            spec_id="SPEC-004",
            contract_digest=digest(contract),
            missing=(),
            warnings=("contract-root-not-object",),
            evidence={"path": contract_path},
        )

    # Parse a valid JSON document as untrusted structured input. A malformed
    # nested object must produce explicit failure evidence, never an exception.
    validator_value = contract.get("canonical_validator")
    if validator_value is not None and not isinstance(validator_value, dict):
        return ContractResult(
            status="FAIL",
            spec_id="SPEC-004",
            contract_digest=digest(contract),
            missing=(),
            warnings=("canonical-validator-not-object",),
            evidence={"path": contract_path},
        )

    vectors_value = contract.get("required_vectors")
    if vectors_value is not None and not isinstance(vectors_value, list):
        return ContractResult(
            status="FAIL",
            spec_id="SPEC-004",
            contract_digest=digest(contract),
            missing=(),
            warnings=("required-vectors-not-list",),
            evidence={"path": contract_path},
        )

    policy_value = contract.get("promotion_policy")
    if policy_value is not None and not isinstance(policy_value, dict):
        return ContractResult(
            status="FAIL",
            spec_id="SPEC-004",
            contract_digest=digest(contract),
            missing=(),
            warnings=("promotion-policy-not-object",),
            evidence={"path": contract_path},
        )

    missing: list[str] = []
    warnings: list[str] = []

    if contract.get("spec_id") != "SPEC-004":
        missing.append("spec-id:SPEC-004")

    validator = validator_value or {}
    validator_path = validator.get("path")
    validator_command = validator.get("command") or []
    validator_hash = validator.get("sha256")

    if not validator_path:
        missing.append("canonical-validator.path")
    if not isinstance(validator_command, list) or not validator_command:
        missing.append("canonical-validator.command")
    if not validator_hash:
        missing.append("canonical-validator.sha256")

    validator_exists = False
    validator_digest = None
    if validator_path:
        validator_file = (repo_root / str(validator_path)).resolve()
        try:
            validator_file.relative_to(repo_root)
        except ValueError:
            missing.append("canonical-validator.path-escapes-root")
        else:
            validator_exists = validator_file.is_file()
            if not validator_exists:
                missing.append(f"canonical-validator.missing:{validator_path}")
            elif validator_hash:
                validator_digest = _sha256_file(validator_file)
                if validator_digest != str(validator_hash):
                    missing.append("canonical-validator.sha256-mismatch")

    vectors = vectors_value or []
    by_id = {str(v.get("id")): v for v in vectors if isinstance(v, dict)}
    vector_evidence: list[dict[str, Any]] = []
    for vector_id in REQUIRED_VECTOR_IDS:
        vector = by_id.get(vector_id)
        if not vector:
            missing.append(f"vector:{vector_id}:declaration")
            vector_evidence.append({"id": vector_id, "status": "MISSING", "reason": "not-declared"})
            continue

        vector_path = vector.get("path")
        vector_hash = vector.get("sha256")
        if not vector_path:
            missing.append(f"vector:{vector_id}:path")
            vector_evidence.append({"id": vector_id, "status": "BLOCKED", "reason": "path-not-declared"})
            continue
        if not vector_hash:
            missing.append(f"vector:{vector_id}:sha256")
            vector_evidence.append({"id": vector_id, "status": "BLOCKED", "reason": "hash-not-declared"})
            continue

        vector_file = (repo_root / str(vector_path)).resolve()
        try:
            vector_file.relative_to(repo_root)
        except ValueError:
            missing.append(f"vector:{vector_id}:path-escapes-root")
            vector_evidence.append({"id": vector_id, "status": "FAIL", "reason": "path-escapes-root"})
            continue

        if not vector_file.is_file():
            missing.append(f"vector:{vector_id}:missing")
            vector_evidence.append({"id": vector_id, "status": "MISSING", "path": vector_path})
            continue

        observed = _sha256_file(vector_file)
        if observed != str(vector_hash):
            missing.append(f"vector:{vector_id}:sha256-mismatch")
            vector_evidence.append({
                "id": vector_id,
                "status": "FAIL",
                "path": vector_path,
                "observed_sha256": observed,
            })
        else:
            vector_evidence.append({
                "id": vector_id,
                "status": "PASS",
                "path": vector_path,
                "sha256": observed,
            })

    if contract.get("canonical_encoding") is None:
        missing.append("canonical-encoding-semantics")
    if contract.get("audit_preimage_semantics") is None:
        missing.append("audit-preimage-semantics")

    if (policy_value or {}).get("bootstrap_must_never_promote_to_canonical") is not True:
        warnings.append("promotion-policy.bootstrap-must-never-promote-to-canonical-not-explicit")

    evidence = {
        "contract_path": contract_path,
        "validator": {
            "path": validator_path,
            "exists": validator_exists,
            "declared_sha256": validator_hash,
            "observed_sha256": validator_digest,
            "command": validator_command,
        },
        "vectors": vector_evidence,
        "required_vector_ids": list(REQUIRED_VECTOR_IDS),
    }

    return ContractResult(
        status="PASS" if not missing else "BLOCKED",
        spec_id=str(contract.get("spec_id", "SPEC-004")),
        contract_digest=digest(contract),
        missing=tuple(sorted(set(missing))),
        warnings=tuple(sorted(set(warnings))),
        evidence=evidence,
    )


def run_declared_validator(repo_root: Path, contract: dict[str, Any], timeout_seconds: int = 120) -> dict[str, Any]:
    """Execute only the validator command declared by the trusted contract."""
    validator = contract.get("canonical_validator") or {}
    command = validator.get("command") or []
    if not isinstance(command, list) or not command:
        return {"status": "BLOCKED", "reason": "validator-command-not-declared"}
    if not all(isinstance(part, str) for part in command):
        return {"status": "BLOCKED", "reason": "validator-command-malformed"}

    result = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "command": command,
        "stdout_tail": result.stdout[-5000:],
        "stderr_tail": result.stderr[-3000:],
    }


def evaluate(repo_root: Path) -> dict[str, Any]:
    result = inspect_contract(repo_root)
    return result.as_dict()

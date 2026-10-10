#!/usr/bin/env python3
"""
CAIOS Autonomous Proof-Carrying Runtime.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi

This module does not vendor or copy external agent/framework code. It provides
an integration boundary around AETHEL, Safety Kernel, ALGA_FOLD_KERNEL and
optional external coding/model backends.

Core rule:
    MODELS MAY PROPOSE.
    DETERMINISTIC GATES DECIDE.
    EVERY EXECUTED STEP MUST RETURN EVIDENCE.
"""
from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import hashlib
import json
import math
import os
import shlex
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterable

from autonomy.agent_attestation import validate_proposal
from autonomy.agent_router import AgentRegistry
from autonomy.caios_council import CAIOSCouncil
from conformance.contract import inspect_contract
from integrations.remote_interop import RemoteInteropClient
from integrations.tool_compiler import compile_command
from federation.security_primitives import SessionAnchor, SessionAnchorRegistry
from telemetry.caios_events import new_event
from telemetry.event_log import TelemetryLog
from autonomy.context_window import ContextWindow
from autonomy.agent_reputation import AgentReputationStore
from autonomy.circuit_breaker import CircuitBreaker
from autonomy.evidence_ledger import EvidenceLedger
from autonomy.egress_policy import EgressPolicy, scan_context
from autonomy.sandbox_simulator import DisposableWorktree
from autonomy.proof_work_contract import ProofCarryingWorkContract
from autonomy.proof_work_verifier import verify_contract
from autonomy.protocol_conformance import ProtocolConformanceRunner
from autonomy.authority_lattice import AuthorityLattice


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _normalize_unit_metrics(item: dict[str, Any]) -> dict[str, float] | None:
    """Validate proposal metrics before coercion, rejecting bools and huge integers."""
    defaults = {
        "expected_gain": 0.30,
        "risk": 0.50,
        "reversibility": 0.60,
        "resource_cost": 0.30,
        "evidence_gain": 0.50,
    }
    metrics: dict[str, float] = {}
    for name, default in defaults.items():
        value = item.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if isinstance(value, int):
            # Do not convert arbitrary-size integers to float before bounds checking.
            if value < 0 or value > 1:
                return None
            metrics[name] = float(value)
            continue
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            return None
        metrics[name] = value
    return metrics


def _normalize_model_command(value: Any) -> tuple[str, ...] | None:
    """Parse an optional model command without allowing malformed input to escape."""
    if value is None or value == "":
        return ()
    if not isinstance(value, str):
        return None
    if not value.strip():
        return ()
    try:
        argv = tuple(shlex.split(value))
    except ValueError:
        return None
    return argv if argv else None


def _normalize_string_list(value: Any) -> tuple[str, ...] | None:
    """Accept JSON arrays of non-empty strings only for invariant/tool identifiers."""
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        return None
    return tuple(value)


def _is_test_file_path(path: str) -> bool:
    candidate = Path(path)
    basename = candidate.name.lower()
    test_names = (
        "test_*.py",
        "*_test.py",
        "*.test.py",
        "*.spec.py",
        "*.test.js",
        "*.spec.js",
        "*.test.ts",
        "*.spec.ts",
        "test_*.rs",
        "*_test.rs",
        "*_test.go",
    )
    return (
        any(part.lower() in {"test", "tests"} for part in candidate.parts[:-1])
        or any(fnmatch.fnmatch(basename, pattern) for pattern in test_names)
    )


def _is_build_control_file(path: str) -> bool:
    name = Path(path).name.lower()
    fixed_names = {
        ".gitmodules",
        "pyproject.toml",
        "pytest.ini",
        "tox.ini",
        "setup.cfg",
        "setup.py",
        "conftest.py",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "cargo.toml",
        "cargo.lock",
        "uv.lock",
        "pipfile",
        "pipfile.lock",
        "makefile",
        "justfile",
        "dockerfile",
        "docker-compose.yml",
    }
    return name in fixed_names or (name.startswith("requirements") and name.endswith(".txt"))


@dataclasses.dataclass(frozen=True)
class Evidence:
    kind: str
    status: str
    source: str
    digest: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class CandidateAction:
    action_id: str
    kind: str
    target: str
    rationale: str
    expected_gain: float
    risk: float
    reversibility: float
    resource_cost: float
    evidence_gain: float
    command: tuple[str, ...] = ()
    unified_diff: str = ""
    agent_id: str | None = None
    protocol: str | None = "caios-internal"
    protocol_version: str | None = "1"
    model_id: str | None = None
    model_revision: str | None = None
    attestation_digest: str | None = None
    invariant_ids: tuple[str, ...] = ()
    tool_ids: tuple[str, ...] = ()
    authority_principal: str = "caios"

    @property
    def fingerprint(self) -> str:
        return digest(dataclasses.asdict(self))

    @property
    def intent_fingerprint(self) -> str:
        return digest({
            "kind": self.kind,
            "target": self.target,
            "command": list(self.command),
            "unified_diff": self.unified_diff,
        })


@dataclasses.dataclass(frozen=True)
class DecisionCertificate:
    cycle: int
    selected_action: str | None
    decision: str
    score: float
    gaps_before: dict[str, float]
    evidence: tuple[Evidence, ...]
    reasons: tuple[str, ...]
    action_fingerprint: str | None
    previous_certificate_digest: str | None
    elapsed_ms: int
    observation_digest: str | None = None
    council_digest: str | None = None
    session_id: str | None = None
    session_anchor_hash: str | None = None
    work_contract_digest: str | None = None

    @property
    def proof_digest(self) -> str:
        return digest({
            "cycle": self.cycle,
            "selected_action": self.selected_action,
            "decision": self.decision,
            "score": self.score,
            "gaps_before": self.gaps_before,
            "evidence": [e.as_dict() for e in self.evidence],
            "reasons": list(self.reasons),
            "action_fingerprint": self.action_fingerprint,
            "previous_certificate_digest": self.previous_certificate_digest,
            "elapsed_ms": self.elapsed_ms,
            "observation_digest": self.observation_digest,
            "council_digest": self.council_digest,
            "session_id": self.session_id,
            "session_anchor_hash": self.session_anchor_hash,
            "work_contract_digest": self.work_contract_digest,
        })

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "selected_action": self.selected_action,
            "decision": self.decision,
            "score": self.score,
            "gaps_before": self.gaps_before,
            "evidence": [e.as_dict() for e in self.evidence],
            "reasons": list(self.reasons),
            "action_fingerprint": self.action_fingerprint,
            "previous_certificate_digest": self.previous_certificate_digest,
            "elapsed_ms": self.elapsed_ms,
            "observation_digest": self.observation_digest,
            "council_digest": self.council_digest,
            "session_id": self.session_id,
            "session_anchor_hash": self.session_anchor_hash,
            "work_contract_digest": self.work_contract_digest,
            "proof_digest": self.proof_digest,
        }


class SafeCommandRunner:
    """Executes only explicit argv vectors; no shell parsing is permitted."""

    def __init__(self, repo_root: Path, timeout_seconds: int = 120) -> None:
        self.repo_root = repo_root.resolve()
        self.timeout_seconds = timeout_seconds

    def run(self, argv: Iterable[str]) -> tuple[int, str, str]:
        args = tuple(str(x) for x in argv)
        if not args:
            raise ValueError("empty command")
        proc = subprocess.run(
            args,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent an approved endpoint from redirecting source context elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


MAX_PROVIDER_RESPONSE_BYTES = 2_000_000
MAX_PROVIDER_PROPOSALS = 20


class OpenAICompatibleProposalProvider:
    """
    Optional model adapter.

    The endpoint is expected to return a JSON object:
      {"proposals": [{"kind": "...", "target": "...", ...}]}

    The runtime never executes raw model text. Only schema-valid proposal
    objects reach the deterministic policy gate.
    """

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str | None = None,
        send_source_context: bool = False,
    ) -> None:
        try:
            parsed = urllib.parse.urlsplit(endpoint)
            hostname = parsed.hostname
            # Accessing .port validates malformed / out-of-range port text.
            _ = parsed.port
        except (TypeError, ValueError) as exc:
            raise ValueError("model endpoint URL is malformed") from exc
        if parsed.scheme not in {"https", "http"} or not hostname:
            raise ValueError("model endpoint must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("model endpoint must not contain credentials, query parameters, or fragments")
        if parsed.scheme == "http" and hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("non-local model endpoints must use HTTPS")
        if not isinstance(send_source_context, bool):
            raise ValueError("send_source_context must be a boolean")
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        # Do not inherit HTTP(S)_PROXY from the process environment. The
        # configured, registry-bound endpoint is the only allowed destination.
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirectHandler(),
        )
        self.send_source_context = send_source_context
        self.egress_policy = EgressPolicy(
            allow_source_context=self.send_source_context,
        )
        self.last_egress = None

    def propose(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        model_snapshot = dict(snapshot)
        if not self.send_source_context:
            model_snapshot.pop("source_context", None)
        egress = scan_context(
            model_snapshot,
            self.egress_policy,
            source_context=self.send_source_context,
        )
        self.last_egress = egress
        if egress.status != "ALLOW":
            raise PermissionError(
                "model context egress blocked: "
                + ",".join(egress.reasons)
            )

        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return JSON only. You are a proposal engine, not an execution authority. "
                        "Generate small, reversible, evidence-producing actions. Never claim a test passed "
                        "without evidence. Never request arbitrary shell access. Every proposal must declare "
                        "agent_id, protocol, model_id, agent_version, and source_ref."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(model_snapshot, sort_keys=True),
                },
            ],
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        with self.opener.open(req, timeout=45) as response:
            raw_response = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
        if not isinstance(raw_response, (bytes, bytearray)):
            raise ValueError("model response body must be bytes")
        if len(raw_response) > MAX_PROVIDER_RESPONSE_BYTES:
            raise ValueError("model response exceeds maximum byte size")
        try:
            data = json.loads(raw_response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"model response is not valid UTF-8 JSON: {type(exc).__name__}") from exc
        if not isinstance(data, dict):
            raise ValueError("model response must be a JSON object")

        if "proposals" in data:
            rows = data["proposals"]
        elif "choices" in data:
            choices = data["choices"]
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise ValueError("model choices response has an invalid shape")
            message = choices[0].get("message")
            if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                raise ValueError("model choice message content must be a string")
            try:
                parsed = json.loads(message["content"])
            except json.JSONDecodeError as exc:
                raise ValueError("model choice content is not valid JSON") from exc
            if not isinstance(parsed, dict):
                raise ValueError("model choice content must decode to a JSON object")
            rows = parsed.get("proposals", [])
        else:
            return []

        if not isinstance(rows, list):
            raise ValueError("model proposals field must be a JSON array")
        return [row for row in rows if isinstance(row, dict)][:MAX_PROVIDER_PROPOSALS]


class ConstitutionalGate:
    """Deterministic deny-by-default action gate."""

    ALLOWED_KINDS = {
        "observe",
        "run_test",
        "run_security_scan",
        "rebuild_state",
        "verify_conformance",
        "apply_patch",
        "human_review",
    }

    MANDATORY_PROTECTED_GLOBS = (
        ".github/workflows/**",
        "conformance/**",
        "autonomy/caios_runtime.py",
        "autonomy/protected_surfaces.json",
        "autonomy/verify_certificates.py",
        "autonomy/proof_work_contract.py",
        "autonomy/proof_work_verifier.py",
        "autonomy/authority_lattice.py",
        "autonomy/authority_lattice.json",
        "autonomy/agent_attestation.py",
        "autonomy/model_admission.py",
        "autonomy/protocol_admission.py",
        "autonomy/protocol_registry.json",
        "autonomy/agent_registry.json",
        "autonomy/model_registry.json",
        "autonomy/egress_policy.py",
        "autonomy/context_window.py",
        "autonomy/sandbox_simulator.py",
        "autonomy/circuit_breaker.py",
        "autonomy/promotion_gate.py",
        "autonomy/system_readiness.py",
        "autonomy/slsa_verifier.py",
        "autonomy/slsa_provenance.py",
        "autonomy/evidence_ledger.py",
        "autonomy/red_team.py",
        "autonomy/test_caios_runtime.py",
        "autonomy/test_protected_surfaces.py",
        "autonomy/test_egress_policy.py",
        "autonomy/test_context_window.py",
        "autonomy/test_sandbox_simulator.py",
        "autonomy/test_promotion_gate.py",
        "autonomy/test_system_readiness.py",
        "autonomy/test_evidence_ledger.py",
        "autonomy/test_slsa_verifier.py",
        "autonomy/test_red_team.py",
        "autonomy/patch_proposal.py",
        "autonomy/test_patch_proposal.py",
        "autonomy/validate_patch_proposal.py",
        "autonomy/test_validate_patch_proposal.py",
        "autonomy/test_multi_agent_provider.py",
        "autonomy/test_proposal_context.py",
        "federation/system_manifest.json",
        "federation/portfolio_ci_parity.py",
        "federation/test_portfolio_ci_parity.py",
        "autonomy/agent_endpoints.json",
        "autonomy/provider_endpoint_registry.json",
        "integrations/tool_compiler.py",
        "integrations/tool_registry.py",
        "integrations/caios_tool_registry.json",
        "federation/security_primitives.py",
        "federation/node_identity.py",
        "federation/signed_envelope.py",
    )

    def __init__(
        self,
        repo_root: Path,
        max_patch_lines: int = 250,
        max_patch_chars: int = 1_000_000,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.max_patch_lines = max_patch_lines
        self.max_patch_chars = max_patch_chars
        self.authority = AuthorityLattice(self.repo_root)
        policy_path = self.repo_root / "autonomy" / "protected_surfaces.json"
        self.protected_policy_valid = False
        configured_globs: tuple[str, ...] = ()
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            globs = policy.get("protected_globs") if isinstance(policy, dict) else None
            if (
                not isinstance(globs, list)
                or not globs
                or any(not isinstance(item, str) or not item.strip() for item in globs)
            ):
                raise ValueError("protected_globs must be a non-empty list of non-empty strings")
            configured_globs = tuple(globs)
            self.protected_policy_valid = True
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            # Preserve baseline protections for inspection, but refuse all
            # autonomous patches until the configuration can be trusted.
            self.protected_policy_valid = False

        self.protected_globs = tuple(dict.fromkeys(
            (*self.MANDATORY_PROTECTED_GLOBS, *configured_globs)
        ))

    def validate(self, action: CandidateAction) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if not isinstance(action.kind, str):
            reasons.append("action kind must be a string in the allowlist")
        elif action.kind not in self.ALLOWED_KINDS:
            reasons.append(f"action kind '{action.kind}' is not in the allowlist")

        numeric_fields = {
            "expected_gain": action.expected_gain,
            "risk": action.risk,
            "reversibility": action.reversibility,
            "resource_cost": action.resource_cost,
            "evidence_gain": action.evidence_gain,
        }
        for field, value in numeric_fields.items():
            valid_number = (
                not isinstance(value, bool)
                and isinstance(value, (int, float))
            )
            if valid_number and isinstance(value, float):
                valid_number = math.isfinite(value)
            # Compare arbitrary-size ints directly; math.isfinite(int) can
            # raise OverflowError while converting a hostile integer to float.
            if valid_number:
                valid_number = 0.0 <= value <= 1.0
            if not valid_number:
                reasons.append(f"{field} must be finite and within [0,1]")

        if (
            not isinstance(action.target, str)
            or any(ord(char) < 0x20 or ord(char) == 0x7f for char in action.target)
        ):
            reasons.append("target contains unsupported control characters")
        else:
            try:
                target = (self.repo_root / action.target).resolve()
                target.relative_to(self.repo_root)
            except ValueError as exc:
                if "embedded null byte" in str(exc).lower():
                    reasons.append("target contains unsupported control characters")
                else:
                    reasons.append("target escapes repository root")
            except (OSError, RuntimeError) as exc:
                reasons.append(f"target resolution failed closed: {type(exc).__name__}")

        if isinstance(action.risk, (int, float)) and not isinstance(action.risk, bool) and action.risk > 0.85:
            reasons.append("risk exceeds autonomous threshold")
        if (
            isinstance(action.reversibility, (int, float))
            and not isinstance(action.reversibility, bool)
            and action.reversibility < 0.40
            and action.kind != "human_review"
        ):
            reasons.append("action is insufficiently reversible")
        if not isinstance(action.action_id, str):
            reasons.append("action id must be a string")
        elif (
            isinstance(action.kind, str)
            and action.kind in {"run_test", "run_security_scan"}
            and (
                action.action_id.startswith("model-")
                or action.authority_principal != "caios"
                or action.agent_id is not None
                or action.attestation_digest is not None
            )
        ):
            reasons.append("model-originated actions cannot supply arbitrary executable commands")

        if not isinstance(action.authority_principal, str) or not action.authority_principal:
            reasons.append("authority principal must be a non-empty string")
        else:
            required_capability = "supervise" if action.authority_principal == "caios" else "propose"
            authorized, authority_reason = self.authority.authorize(
                action.authority_principal,
                required_capability,
            )
            if not authorized:
                reasons.append(
                    f"authority principal '{action.authority_principal}' denied {required_capability}: {authority_reason}"
                )

        if action.kind == "apply_patch":
            if not self.protected_policy_valid:
                reasons.append(
                    "protected-surface-policy-unavailable; autonomous patches are denied"
                )
            if not isinstance(action.unified_diff, str):
                reasons.append("patch action unified diff must be a string")
                return False, reasons
            if not action.unified_diff:
                reasons.append("patch action has no unified diff")
            if len(action.unified_diff) > self.max_patch_chars:
                reasons.append("patch exceeds maximum patch size")
                return False, reasons
            # Enforce payload bounds before line splitting or path processing.
            diff_lines = action.unified_diff.splitlines()
            diff_headers = [line for line in diff_lines if line.startswith("diff --git ")]
            old_file_headers = [line[4:].split("\t", 1)[0] for line in diff_lines if line.startswith("--- ")]
            new_file_headers = [line[4:].split("\t", 1)[0] for line in diff_lines if line.startswith("+++ ")]
            if (
                len(diff_headers) != 1
                or len(old_file_headers) != 1
                or len(new_file_headers) != 1
            ):
                reasons.append("patch must contain exactly one file section")
            else:
                git_parts = diff_headers[0].split()
                old_header = old_file_headers[0]
                new_header = new_file_headers[0]
                mismatch = (
                    len(git_parts) != 4
                    or not git_parts[2].startswith("a/")
                    or not git_parts[3].startswith("b/")
                    or (old_header != "/dev/null" and (
                        not old_header.startswith("a/")
                        or len(git_parts) == 4 and old_header[2:] != git_parts[2][2:]
                    ))
                    or (new_header != "/dev/null" and (
                        not new_header.startswith("b/")
                        or len(git_parts) == 4 and new_header[2:] != git_parts[3][2:]
                    ))
                    or (old_header == "/dev/null" and new_header == "/dev/null")
                )
                if mismatch:
                    reasons.append("patch file headers do not match diff header")
            changed_lines = sum(
                1 for line in action.unified_diff.splitlines()
                if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
            )
            if changed_lines > self.max_patch_lines:
                reasons.append("patch exceeds maximum autonomous change budget")
            has_file_header = False
            for line in action.unified_diff.splitlines():
                if line.startswith(("+++ ", "--- ")):
                    has_file_header = True
                    patch_path = line[4:].split("\t", 1)[0]
                    if patch_path == "/dev/null":
                        if line.startswith("+++ "):
                            reasons.append("autonomous patch deletion is not permitted")
                        continue
                    raw_path = patch_path[2:] if patch_path.startswith(("a/", "b/")) else patch_path
                    # Git can interpret quoted path headers; fail closed rather than
                    # comparing an ambiguous literal against protected path globs.
                    if any(ord(char) < 0x20 or 0x7f <= ord(char) <= 0x9f for char in raw_path):
                        reasons.append("patch path contains unsupported control characters")
                        continue
                    if raw_path.startswith('"') or raw_path.endswith('"') or any(char.isspace() for char in raw_path):
                        reasons.append("patch path uses unsupported quoted or whitespace format")
                        continue
                    # Canonicalize separators and dot segments before policy matching.
                    security_path = raw_path.replace("\\", "/")
                    security_parts = tuple(
                        part for part in security_path.split("/")
                        if part not in ("", ".")
                    )
                    has_drive_prefix = (
                        len(security_path) >= 2
                        and security_path[0].isalpha()
                        and security_path[1] == ":"
                    )
                    if (
                        security_path.startswith("/")
                        or has_drive_prefix
                        or any(part == ".." for part in security_parts)
                        or any(part.casefold() == ".git" for part in security_parts)
                    ):
                        reasons.append("patch path escapes or targets git internals")
                        continue
                    normalized = "/".join(security_parts)
                    if not normalized:
                        reasons.append("patch path is empty or not parseable")
                        continue

                    # Lexical checks do not stop a path that crosses an existing
                    # symlinked directory. Resolve every patch path against the
                    # checkout and fail closed when it reaches outside the repo.
                    try:
                        resolved_patch_path = (self.repo_root / normalized).resolve()
                        resolved_patch_path.relative_to(self.repo_root)
                    except ValueError:
                        reasons.append("patch path resolves outside repository root")
                    except (OSError, RuntimeError) as exc:
                        reasons.append(
                            f"patch path resolution failed closed: {type(exc).__name__}"
                        )

                    # Normalize case for portable fail-closed matching on
                    # case-insensitive filesystems (e.g. default Windows volumes).
                    if any(
                        fnmatch.fnmatch(normalized.casefold(), pattern.casefold())
                        for pattern in self.protected_globs
                    ):
                        reasons.append("patch targets protected autonomous-control surface")
                    if _is_build_control_file(normalized):
                        reasons.append("patch targets protected build or test configuration")
                    if (
                        line.startswith("--- ")
                        and _is_test_file_path(normalized)
                        and (self.repo_root / normalized).is_file()
                    ):
                        reasons.append("patch modifies an existing test file")
            if not has_file_header:
                reasons.append("patch has no parseable file headers")

        return not reasons, reasons


class AethelObserver:
    """Uses the local AETHEL interop service when available."""

    def observe(self, repo_root: Path) -> list[Evidence]:
        evidence: list[Evidence] = []
        service = repo_root / "interop" / "aethel_service.py"
        if not service.exists():
            return [
                Evidence(
                    kind="aethel",
                    status="UNKNOWN",
                    source="aethel-grid",
                    digest=digest("missing"),
                    details={"reason": "interop/aethel_service.py not present"},
                )
            ]

        text = service.read_text(encoding="utf-8")
        conformance_blocked = "canonical_validator\": \"not-established" in text or "canonical_conformance" in text
        evidence.append(
            Evidence(
                kind="aethel-runtime",
                status="PASS",
                source=str(service),
                digest=digest(text),
                details={"bootstrap_service_present": True},
            )
        )
        contract = inspect_contract(repo_root)
        evidence.append(
            Evidence(
                kind="canonical-conformance",
                status=contract.status,
                source=str(repo_root / "conformance" / "canonical_contract.json"),
                digest=contract.contract_digest,
                details={
                    "missing": list(contract.missing),
                    "warnings": list(contract.warnings),
                    "evidence": contract.evidence,
                },
            )
        )
        if conformance_blocked and contract.status == "PASS":
            evidence.append(
                Evidence(
                    kind="canonical-promotion-guard",
                    status="BLOCKED",
                    source=str(service),
                    digest=digest("bootstrap-cannot-promote"),
                    details={"reason": "bootstrap source still declares canonical conformance as unresolved"},
                )
            )
        return evidence


class RemoteEvidenceObserver:
    """Optionally queries configured sibling services through aethel-interop/1."""

    def observe(self, repo_root: Path) -> list[Evidence]:
        config_path = repo_root / "integrations" / "remote_evidence.json"
        if not config_path.is_file():
            return []

        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return [
                Evidence(
                    kind="remote-interop",
                    status="FAIL",
                    source=str(config_path),
                    digest=digest(str(exc)),
                    details={"exception": type(exc).__name__, "message": str(exc)},
                )
            ]

        evidence = []
        for entry in config.get("endpoints", []):
            endpoint_id = str(entry.get("id", "unknown"))
            url_env = str(entry.get("url_env", ""))
            url = os.getenv(url_env, "").strip()
            if not url:
                evidence.append(
                    Evidence(
                        kind="remote-interop",
                        status="UNKNOWN",
                        source=endpoint_id,
                        digest=digest({"id": endpoint_id, "url_env": url_env, "configured": False}),
                        details={"configured": False, "url_env": url_env},
                    )
                )
                continue

            try:
                token_env = str(entry.get("token_env", ""))
                token = os.getenv(token_env) if token_env else None
                client = RemoteInteropClient(url, bearer_token=token)
                operation = str(entry.get("operation", "capabilities"))
                if operation == "health":
                    raw = client.health()
                    evidence.append(
                        Evidence(
                            kind="remote-interop-health",
                            status="PASS",
                            source=endpoint_id,
                            digest=digest(raw),
                            details={"response": raw},
                        )
                    )
                    continue
                if operation == "capabilities":
                    raw = client.capabilities()
                    evidence.append(
                        Evidence(
                            kind="remote-interop-capabilities",
                            status="PASS",
                            source=endpoint_id,
                            digest=digest(raw),
                            details={"response": raw},
                        )
                    )
                    continue

                response = client.evaluate(
                    request_id=f"caios-{int(time.time_ns())}",
                    operation=operation,
                    payload=dict(entry.get("payload", {})),
                )
                evidence.append(
                    Evidence(
                        kind="remote-interop",
                        status="PASS" if response.status == "PASS" else "DEGRADED",
                        source=endpoint_id,
                        digest=response.response_digest,
                        details={
                            "protocol": response.protocol,
                            "service": response.service,
                            "version": response.version,
                            "request_id": response.request_id,
                            "status": response.status,
                            "decision": response.decision,
                            "reasons": list(response.reasons),
                            "evidence": response.evidence,
                        },
                    )
                )
            except Exception as exc:
                evidence.append(
                    Evidence(
                        kind="remote-interop",
                        status="FAIL",
                        source=endpoint_id,
                        digest=digest(str(exc)),
                        details={"exception": type(exc).__name__, "message": str(exc)},
                    )
                )
        return evidence


class RedTeamObserver:
    """Runs a bounded deterministic attack campaign against the gate."""

    def observe(self, repo_root: Path) -> Evidence:
        try:
            from autonomy.red_team import run_campaign
            result = run_campaign(repo_root)
            return Evidence(
                kind="red-team",
                status="PASS" if result["passed"] else "FAIL",
                source="autonomy/red_team.py",
                digest=digest(result),
                details=result,
            )
        except Exception as exc:
            return Evidence(
                kind="red-team",
                status="FAIL",
                source="autonomy/red_team.py",
                digest=digest(str(exc)),
                details={"exception": type(exc).__name__, "message": str(exc)},
            )


class ProtocolObserver:
    """Records admitted protocol revisions and available conformance tools."""

    def observe(self, repo_root: Path) -> Evidence:
        try:
            runner = ProtocolConformanceRunner(repo_root)
            plan = runner.plan()
            return Evidence(
                kind="protocol-surface",
                status="PASS",
                source="autonomy/protocol_conformance.py",
                digest=digest(plan),
                details={"protocols": plan},
            )
        except Exception as exc:
            return Evidence(
                kind="protocol-surface",
                status="FAIL",
                source="autonomy/protocol_conformance.py",
                digest=digest(str(exc)),
                details={"exception": type(exc).__name__, "message": str(exc)},
            )


class AgentObserver:
    """Reports which registered agent families are eligible for the cycle."""

    def observe(self, repo_root: Path, risk: float = 0.60) -> Evidence:
        try:
            registry = AgentRegistry(repo_root)
            capabilities = ("coding", "testing", "patching") if risk >= 0.55 else ("planning", "reasoning")
            reputation = AgentReputationStore(
                repo_root / "ops" / "caios" / "agent-reputation.jsonl"
            )
            plan = registry.plan_quorum(
                capabilities,
                ("acp", "mcp", "openai-compatible"),
                risk,
                evidence=reputation.all_scores(),
                max_agents=3,
            )
            return Evidence(
                kind="agent-arbitration",
                status="PASS" if plan.satisfied else "BLOCKED",
                source="autonomy/agent_registry.json",
                digest=plan.plan_digest,
                details={
                    "required_independent_families": plan.required_independent_families,
                    "satisfied": plan.satisfied,
                    "assignments": [a.__dict__ for a in plan.assignments],
                },
            )
        except Exception as exc:
            return Evidence(
                kind="agent-arbitration",
                status="FAIL",
                source="autonomy/agent_registry.json",
                digest=digest(str(exc)),
                details={"exception": type(exc).__name__, "message": str(exc)},
            )


class FederationObserver:
    """Observes the explicit CAIOS multi-repository manifest when present."""

    def observe(self, repo_root: Path) -> Evidence | None:
        manifest_path = repo_root / "federation" / "system_manifest.json"
        if not manifest_path.exists():
            return None
        try:
            from federation.caios_federation import build_federation

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            snapshot = build_federation(repo_root, manifest, run_verification=False)
            federation_status = "PASS" if all(r["status"] == "PRESENT" for r in snapshot["repositories"]) else "DEGRADED"
            return Evidence(
                kind="federation",
                status=federation_status,
                source=str(manifest_path),
                digest=digest(snapshot),
                details={
                    "system_digest": snapshot["system_digest"],
                    "next_inspection_target": snapshot["next_inspection_target"],
                    "repositories": [
                        {
                            "id": r["id"],
                            "status": r["status"],
                            "cdp": r["constitutional_dependency_pressure"],
                        }
                        for r in snapshot["repositories"]
                    ],
                },
            )
        except Exception as exc:
            return Evidence(
                kind="federation",
                status="FAIL",
                source=str(manifest_path),
                digest=digest(str(exc)),
                details={"exception": type(exc).__name__, "message": str(exc)},
            )


class RepositorySnapshot:
    def __init__(self, runner: SafeCommandRunner) -> None:
        self.runner = runner

    def capture_state_digest(self) -> str:
        head_rc, head_out, _ = self.runner.run(("git", "rev-parse", "HEAD"))
        status_rc, status_out, _ = self.runner.run(("git", "status", "--porcelain"))
        return digest({
            "head": head_out.strip() if head_rc == 0 else None,
            "status": status_out,
        })

    def capture(self) -> dict[str, Any]:
        head_rc, head_out, _ = self.runner.run(("git", "rev-parse", "HEAD"))
        status_rc, status_out, _ = self.runner.run(("git", "status", "--short", "--branch"))
        tracked_rc, tracked_out, _ = self.runner.run(("git", "ls-files"))

        snapshot = {
            "head": head_out.strip() if head_rc == 0 else None,
            "status": status_out.strip() if status_rc == 0 else None,
            "tracked_files": tracked_out.splitlines() if tracked_rc == 0 else [],
        }
        diff_rc, diff_out, _ = self.runner.run(("git", "diff", "--binary", "HEAD"))
        snapshot["working_tree_diff_digest"] = digest(diff_out) if diff_rc == 0 else None
        snapshot["working_tree_dirty"] = bool(
            snapshot["status"]
            and any(line and not line.startswith("##") for line in snapshot["status"].splitlines())
        )
        snapshot["observation_digest"] = digest(snapshot)
        return snapshot


class ViabilityPlanner:
    """
    Selects the next action by maximizing progress and evidence gained per
    unit risk/cost. No model output can override this scoring function.
    """

    def score(self, action: CandidateAction) -> float:
        numerator = (
            4.0 * action.expected_gain
            + 3.0 * action.evidence_gain
            + 2.0 * action.reversibility
        )
        denominator = 1.0 + 5.0 * action.risk + 2.0 * action.resource_cost
        return numerator / denominator

    def select(
        self,
        candidates: list[CandidateAction],
        gate: ConstitutionalGate,
        council_priority: dict[str, float] | None = None,
    ) -> tuple[CandidateAction | None, float, list[str]]:
        best: CandidateAction | None = None
        best_score = float("-inf")
        rejected: list[str] = []
        gap_for_kind = {
            "run_test": "verification",
            "run_security_scan": "security",
            "verify_conformance": "conformance",
            "apply_patch": "integration",
            "observe": "integration",
            "rebuild_state": "verification",
            "human_review": "conformance",
        }
        for candidate in candidates:
            allowed, reasons = gate.validate(candidate)
            if not allowed:
                rejected.append(f"{candidate.action_id}: " + "; ".join(reasons))
                continue
            base_score = self.score(candidate)
            gap = gap_for_kind.get(candidate.kind)
            priority = float((council_priority or {}).get(gap, 0.0)) if gap else 0.0
            score = base_score * (1.0 + 0.35 * max(0.0, min(1.0, priority)))
            if score > best_score:
                best = candidate
                best_score = score
        return best, best_score if best else 0.0, rejected


class AutonomousRuntime:
    """
    Proof-carrying autonomous loop.

    Each cycle:
      OBSERVE -> FORM GAP VECTOR -> GENERATE CANDIDATES -> GATE -> SELECT
      -> EXECUTE -> VERIFY -> RECORD CERTIFICATE -> RE-OBSERVE

    The loop halts if no viable action remains or a human decision is required.
    """

    def __init__(
        self,
        repo_root: Path,
        command_runner: SafeCommandRunner | None = None,
        proposal_provider: Any | None = None,
        max_cycles: int = 5,
        max_commands: int = 20,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.runner = command_runner or SafeCommandRunner(self.repo_root)
        self.snapshotter = RepositorySnapshot(self.runner)
        self.aethel = AethelObserver()
        self.federation = FederationObserver()
        self.agents = AgentObserver()
        self.remote = RemoteEvidenceObserver()
        self.protocols = ProtocolObserver()
        self.red_team = RedTeamObserver()
        self.council = CAIOSCouncil()
        self.authority = AuthorityLattice(self.repo_root)
        self.gate = ConstitutionalGate(self.repo_root)
        self.planner = ViabilityPlanner()
        self.proposal_provider = proposal_provider
        self.max_cycles = max_cycles
        self.max_commands = max_commands
        self.commands_used = 0
        self.certificates: list[DecisionCertificate] = []
        self.last_model_admission: list[dict[str, Any]] = []
        self.reputation = AgentReputationStore(
            self.repo_root / "ops" / "caios" / "agent-reputation.jsonl"
        )
        self.session_id = str(uuid.uuid4())
        self.trace_id = uuid.uuid4().hex
        self.telemetry = TelemetryLog(
            self.repo_root / "ops" / "caios" / "telemetry.jsonl"
        )
        self.anchors = SessionAnchorRegistry(
            self.repo_root / "ops" / "caios" / "session-anchors.jsonl"
        )
        self.evidence_ledger = EvidenceLedger(
            self.repo_root / "ops" / "caios" / "evidence-ledger.jsonl"
        )
        self.circuit = CircuitBreaker(
            self.repo_root / "ops" / "caios" / "circuit-breaker.json"
        )

    def _gap_vector(self, evidence: list[Evidence], snapshot: dict[str, Any]) -> dict[str, float]:
        gaps = {
            "conformance": 0.0,
            "verification": 0.0,
            "integration": 0.0,
            "security": 0.0,
            "working_tree": 0.0,
            "authority": 0.0,
        }
        has_tests = bool(
            (self.repo_root / "tests").exists()
            or (self.repo_root / "interop").exists()
        )
        gaps["verification"] = 1.0 if has_tests else 0.0
        for item in evidence:
            if item.kind == "canonical-conformance" and item.status != "PASS":
                gaps["conformance"] = 1.0
            if item.kind == "test":
                gaps["verification"] = 0.0 if item.status == "PASS" else 1.0
            if item.kind == "security" and item.status != "PASS":
                gaps["security"] = 1.0
            if item.kind == "federation" and item.status != "PASS":
                gaps["integration"] = 1.0
        if snapshot.get("status"):
            gaps["working_tree"] = 0.5 if " M " in snapshot["status"] else 0.0
        if not any(item.kind == "aethel-runtime" and item.status == "PASS" for item in evidence):
            gaps["integration"] = 1.0
        if not any(item.kind == "authority-lattice" and item.status == "PASS" for item in evidence):
            gaps["authority"] = 1.0
        return gaps

    def _baseline_candidates(self, gaps: dict[str, float]) -> list[CandidateAction]:
        candidates: list[CandidateAction] = []
        if gaps["verification"]:
            if (self.repo_root / "interop").exists():
                compiled, _ = compile_command(self.repo_root, "pytest", ("interop",))
            else:
                compiled, _ = compile_command(self.repo_root, "pytest")
            test_command = compiled.argv if compiled else ()
            candidates.append(
                CandidateAction(
                    action_id="run-tests",
                    kind="run_test",
                    target=".",
                    rationale="close the verification gap with machine-observable test evidence",
                    expected_gain=0.80,
                    evidence_gain=0.95,
                    risk=0.10,
                    reversibility=1.0,
                    resource_cost=0.20,
                    command=test_command,
                    tool_ids=("pytest",) if test_command else (),
                )
            )
        if gaps["conformance"]:
            candidates.append(
                CandidateAction(
                    action_id="verify-conformance",
                    kind="verify_conformance",
                    target=".",
                    rationale="canonical conformance is not established; do not promote bootstrap semantics",
                    expected_gain=0.55,
                    evidence_gain=0.90,
                    risk=0.02,
                    reversibility=1.0,
                    resource_cost=0.05,
                )
            )
        if gaps["security"]:
            candidates.append(
                CandidateAction(
                    action_id="security-scan",
                    kind="run_security_scan",
                    target=".",
                    rationale="collect supply-chain/security evidence before further mutation",
                    expected_gain=0.70,
                    evidence_gain=0.90,
                    risk=0.08,
                    reversibility=1.0,
                    resource_cost=0.30,
                )
            )
        if gaps["integration"]:
            candidates.append(
                CandidateAction(
                    action_id="observe-aethel",
                    kind="observe",
                    target="interop/aethel_service.py",
                    rationale="restore an observable AETHEL integration anchor",
                    expected_gain=0.40,
                    evidence_gain=0.70,
                    risk=0.05,
                    reversibility=1.0,
                    resource_cost=0.10,
                )
            )
        if not candidates:
            candidates.append(
                CandidateAction(
                    action_id="rebuild-state",
                    kind="rebuild_state",
                    target=".",
                    rationale="perform a low-risk deterministic state observation before making another change",
                    expected_gain=0.25,
                    evidence_gain=0.50,
                    risk=0.03,
                    reversibility=1.0,
                    resource_cost=0.05,
                )
            )
        return candidates

    def _apply_model_quorum(self, candidates: list[CandidateAction]) -> list[CandidateAction]:
        if not candidates:
            return candidates
        try:
            registry = AgentRegistry(self.repo_root)
            threshold = float(registry.policy.get("high_risk_threshold", 0.55))
            required = int(registry.policy.get("high_risk_min_independent_agents", 2))
        except Exception:
            return []

        families_by_intent: dict[str, set[str]] = {}
        models_by_intent: dict[str, set[str]] = {}
        for candidate in candidates:
            if not candidate.agent_id or candidate.risk < threshold:
                continue
            profile = registry.agents.get(candidate.agent_id)
            if profile:
                families_by_intent.setdefault(candidate.intent_fingerprint, set()).add(profile.family)
                if candidate.model_id:
                    models_by_intent.setdefault(candidate.intent_fingerprint, set()).add(candidate.model_id)

        admitted: list[CandidateAction] = []
        for candidate in candidates:
            if candidate.risk < threshold:
                admitted.append(candidate)
                continue
            families = families_by_intent.get(candidate.intent_fingerprint, set())
            models = models_by_intent.get(candidate.intent_fingerprint, set())
            model_required = int(registry.policy.get("high_risk_min_independent_models", 2))
            if len(families) >= required and len(models) >= model_required:
                self.last_model_admission.append({
                    "action": candidate.action_id,
                    "status": "ADMITTED",
                    "independent_families": sorted(families),
                })
                admitted.append(candidate)
            else:
                self.last_model_admission.append({
                    "action": candidate.action_id,
                    "status": "QUORUM_REJECTED",
                    "independent_families": sorted(families),
                    "independent_models": sorted(models),
                    "required_independent_families": required,
                    "required_independent_models": model_required,
                })
        return admitted

    def _model_candidates(self, snapshot: dict[str, Any], gaps: dict[str, float]) -> list[CandidateAction]:
        # Admission evidence is scoped to a single cycle. Never allow prior
        # cycle outcomes to survive a provider failure or missing provider.
        self.last_model_admission = []
        if not self.proposal_provider:
            return []
        try:
            model_input = {
                "snapshot": snapshot,
                "gaps": gaps,
                "source_context": ContextWindow(self.repo_root).build(),
            }
            raw = self.proposal_provider.propose(model_input)
        except Exception as exc:
            self.last_model_admission.append({
                "index": None,
                "status": "PROVIDER_FAILED",
                "reasons": [f"proposal-provider-failed:{type(exc).__name__}"],
            })
            return []
        if not isinstance(raw, list):
            self.last_model_admission.append({
                "index": None,
                "status": "REJECTED",
                "reasons": ["proposal-provider-response-not-list"],
            })
            return []

        worker_errors = getattr(self.proposal_provider, "last_errors", [])
        if isinstance(worker_errors, list):
            for error in worker_errors[:20]:
                if not isinstance(error, dict):
                    continue
                agent_id = error.get("agent_id", "")
                error_type = error.get("error_type", "Exception")
                self.last_model_admission.append({
                    "index": None,
                    "agent_id": agent_id if isinstance(agent_id, str) else "",
                    "status": "PROVIDER_FAILED",
                    "reasons": [
                        "proposal-worker-failed:"
                        + (error_type if isinstance(error_type, str) else "Exception")
                    ],
                })
        candidates: list[CandidateAction] = []
        for idx, item in enumerate(raw[:20]):
            if not isinstance(item, dict):
                self.last_model_admission.append({
                    "index": idx,
                    "status": "REJECTED",
                    "reasons": ["proposal-not-object"],
                })
                continue
            try:
                proposal_digest = digest(item)
            except (TypeError, ValueError, OverflowError, RecursionError) as exc:
                self.last_model_admission.append({
                    "index": idx,
                    "status": "REJECTED",
                    "reasons": [f"proposal-canonicalization-failed:{type(exc).__name__}"],
                })
                continue
            admitted, reasons, attestation = validate_proposal(
                self.repo_root, item, proposal_digest
            )
            if not admitted or attestation is None:
                self.last_model_admission.append({
                    "index": idx,
                    "status": "REJECTED",
                    "reasons": reasons,
                    "proposal_digest": proposal_digest,
                })
                continue
            self.last_model_admission.append({
                "index": idx,
                "status": "ATTESTED",
                "agent_id": attestation.agent_id,
                "protocol": attestation.protocol,
                "attestation_digest": attestation.attestation_digest,
            })
            kind = item.get("kind", "human_review")
            target = item.get("target", ".")
            rationale = item.get("rationale", "model proposal")
            diff = item.get("unified_diff", "")
            proposed_action_id = item.get("action_id", "proposal")
            if not all(isinstance(value, str) for value in (kind, target, rationale, diff, proposed_action_id)):
                self.last_model_admission.append({
                    "index": idx,
                    "status": "REJECTED",
                    "reasons": ["proposal-action-fields-must-be-strings"],
                    "proposal_digest": proposal_digest,
                })
                continue
            command = _normalize_model_command(item.get("command"))
            if command is None:
                self.last_model_admission.append({
                    "index": idx,
                    "status": "REJECTED",
                    "reasons": ["proposal-command-malformed"],
                    "proposal_digest": proposal_digest,
                })
                continue
            invariant_ids = _normalize_string_list(item.get("invariant_ids", []))
            tool_ids = _normalize_string_list(item.get("tool_ids", []))
            if invariant_ids is None or tool_ids is None:
                self.last_model_admission.append({
                    "index": idx,
                    "status": "REJECTED",
                    "reasons": ["proposal-invariant-or-tool-ids-malformed"],
                    "proposal_digest": proposal_digest,
                })
                continue
            metrics = _normalize_unit_metrics(item)
            if metrics is None:
                self.last_model_admission.append({
                    "index": idx,
                    "status": "REJECTED",
                    "reasons": ["proposal-metrics-malformed"],
                    "proposal_digest": proposal_digest,
                })
                continue
            candidates.append(
                CandidateAction(
                    action_id=f"model-{idx}-{proposed_action_id}",
                    kind=kind,
                    target=target,
                    rationale=rationale,
                    expected_gain=metrics["expected_gain"],
                    risk=metrics["risk"],
                    reversibility=metrics["reversibility"],
                    resource_cost=metrics["resource_cost"],
                    evidence_gain=metrics["evidence_gain"],
                    command=command,
                    unified_diff=diff,
                    agent_id=attestation.agent_id,
                    protocol=attestation.protocol,
                    protocol_version=attestation.protocol_version,
                    model_id=attestation.model_id,
                    model_revision=attestation.model_revision,
                    attestation_digest=attestation.attestation_digest,
                    invariant_ids=invariant_ids,
                    tool_ids=tool_ids,
                    authority_principal="model",
                )
            )
        return self._apply_model_quorum(candidates)

    def _execute(self, action: CandidateAction) -> list[Evidence]:
        if self.commands_used >= self.max_commands:
            return [
                Evidence(
                    kind="budget",
                    status="BLOCKED",
                    source="caios-runtime",
                    digest=digest("command-budget"),
                    details={"max_commands": self.max_commands},
                )
            ]

        if action.kind in {"observe", "rebuild_state"}:
            snapshot = self.snapshotter.capture()
            self.commands_used += 3
            return [
                Evidence(
                    kind="repository-state",
                    status="PASS",
                    source="git",
                    digest=digest(snapshot),
                    details=snapshot,
                )
            ]

        if action.kind == "run_test":
            command = action.command or ("python", "-m", "pytest", "-q")
            rc, stdout, stderr = self.runner.run(command)
            self.commands_used += 1
            return [
                Evidence(
                    kind="test",
                    status="PASS" if rc == 0 else "FAIL",
                    source=" ".join(command),
                    digest=digest({"rc": rc, "stdout": stdout, "stderr": stderr}),
                    details={"returncode": rc, "stdout_tail": stdout[-2000:], "stderr_tail": stderr[-2000:]},
                )
            ]

        if action.kind == "run_security_scan":
            command = action.command
            if not command:
                return [
                    Evidence(
                        kind="security",
                        status="BLOCKED",
                        source="caios-runtime",
                        digest=digest("no-security-command"),
                        details={"reason": "configure an explicit scanner command (e.g. Scorecard/Grype/Syft)"},
                    )
                ]
            rc, stdout, stderr = self.runner.run(command)
            self.commands_used += 1
            return [
                Evidence(
                    kind="security",
                    status="PASS" if rc == 0 else "FAIL",
                    source=" ".join(command),
                    digest=digest({"rc": rc, "stdout": stdout, "stderr": stderr}),
                    details={"returncode": rc, "stdout_tail": stdout[-2000:], "stderr_tail": stderr[-2000:]},
                )
            ]

        if action.kind == "apply_patch":
            status_rc, status_out, status_err = self.runner.run(("git", "status", "--porcelain"))
            self.commands_used += 1
            if status_rc != 0 or status_out.strip():
                return [
                    Evidence(
                        kind="patch",
                        status="BLOCKED",
                        source="git status",
                        digest=digest(status_out or status_err),
                        details={"reason": "autonomous patching requires a clean working tree"},
                    )
                ]
            test_command = (
                ("python", "-m", "pytest", "-q", "interop")
                if (self.repo_root / "interop").exists()
                else (("python", "-m", "pytest", "-q", "tests") if (self.repo_root / "tests").exists() else ())
            )
            if not test_command:
                return [
                    Evidence(
                        kind="patch",
                        status="BLOCKED",
                        source="caios-runtime",
                        digest=digest("no-validation-suite"),
                        details={"reason": "mutation requires a deterministic validation suite"},
                    )
                ]
            if self.commands_used + 4 > self.max_commands:
                return [
                    Evidence(
                        kind="budget",
                        status="BLOCKED",
                        source="caios-runtime",
                        digest=digest("patch-validation-budget"),
                        details={"max_commands": self.max_commands},
                    )
                ]

            simulation = DisposableWorktree(self.repo_root).run(
                action.unified_diff,
                test_command,
            )
            if simulation.status != "PASS":
                return [
                    Evidence(
                        kind="patch-simulation",
                        status="FAIL",
                        source="autonomy/sandbox_simulator.py",
                        digest=digest(simulation.as_dict()),
                        details=simulation.as_dict(),
                    )
                ]
            self.commands_used += 1

            check = self.repo_root / ".caios-pending.patch"
            check.write_text(action.unified_diff, encoding="utf-8")
            applied = False
            validated = False
            try:
                rc, _, stderr = self.runner.run(("git", "apply", "--check", str(check)))
                self.commands_used += 1
                if rc != 0:
                    return [
                        Evidence(
                            kind="patch",
                            status="FAIL",
                            source="git apply --check",
                            digest=digest(stderr),
                            details={"stderr": stderr[-4000:]},
                        )
                    ]

                rc, _, stderr = self.runner.run(("git", "apply", str(check)))
                self.commands_used += 1
                if rc != 0:
                    return [
                        Evidence(
                            kind="patch",
                            status="FAIL",
                            source="git apply",
                            digest=digest(stderr),
                            details={"stderr": stderr[-4000:]},
                        )
                    ]
                applied = True

                rc, stdout, stderr = self.runner.run(test_command)
                self.commands_used += 1
                if rc == 0:
                    validated = True
                    return [
                        Evidence(
                            kind="patch-simulation",
                            status="PASS",
                            source="autonomy/sandbox_simulator.py",
                            digest=digest(simulation.as_dict()),
                            details={
                                "validation_returncode": simulation.validation_returncode,
                                "stdout_tail": simulation.stdout_tail,
                                "stderr_tail": simulation.stderr_tail,
                            },
                        ),
                        Evidence(
                            kind="patch",
                            status="PASS",
                            source="git apply + validation",
                            digest=digest(action.unified_diff),
                            details={"changed": True, "validation_command": list(test_command)},
                        ),
                        Evidence(
                            kind="test",
                            status="PASS",
                            source=" ".join(test_command),
                            digest=digest({"rc": rc, "stdout": stdout, "stderr": stderr}),
                            details={"returncode": rc, "stdout_tail": stdout[-3000:], "stderr_tail": stderr[-3000:]},
                        ),
                    ]

                reverse_rc, _, reverse_err = self.runner.run(("git", "apply", "-R", str(check)))
                self.commands_used += 1
                applied = False
                return [
                    Evidence(
                        kind="patch",
                        status="FAIL",
                        source="git apply + validation",
                        digest=digest({"patch": action.unified_diff, "validation_rc": rc, "reverse_rc": reverse_rc}),
                        details={
                            "changed": False,
                            "validation_command": list(test_command),
                            "validation_stderr": stderr[-3000:],
                            "rollback_returncode": reverse_rc,
                            "rollback_stderr": reverse_err[-2000:],
                        },
                    ),
                    Evidence(
                        kind="test",
                        status="FAIL",
                        source=" ".join(test_command),
                        digest=digest({"rc": rc, "stdout": stdout, "stderr": stderr}),
                        details={"returncode": rc, "stdout_tail": stdout[-3000:], "stderr_tail": stderr[-3000:]},
                    ),
                ]
            finally:
                if applied and not validated:
                    self.runner.run(("git", "apply", "-R", str(check)))
                    self.commands_used += 1
                check.unlink(missing_ok=True)

        if action.kind == "verify_conformance":
            result = inspect_contract(self.repo_root)
            return [
                Evidence(
                    kind="canonical-conformance",
                    status=result.status,
                    source="conformance/canonical_contract.json",
                    digest=result.contract_digest,
                    details=result.as_dict(),
                )
            ]

        return [
            Evidence(
                kind="human",
                status="REQUIRED",
                source="caios-runtime",
                digest=digest(action.action_id),
                details={"reason": action.rationale},
            )
        ]

    def _build_work_contract(
        self,
        action: CandidateAction,
        snapshot: dict[str, Any],
        action_evidence: list[Evidence],
        decision: str,
    ) -> tuple[ProofCarryingWorkContract, Evidence]:
        state_after = None
        if self.commands_used + 2 <= self.max_commands:
            try:
                state_after = self.snapshotter.capture_state_digest()
                self.commands_used += 2
            except Exception:
                state_after = None

        simulation_digest = next(
            (item.digest for item in action_evidence if item.kind == "patch-simulation"),
            None,
        )
        contract = ProofCarryingWorkContract(
            work_id=f"{self.session_id}:{action.action_id}",
            intent_fingerprint=action.intent_fingerprint,
            action_kind=action.kind,
            state_before=snapshot["observation_digest"],
            state_after=state_after,
            protocol=action.protocol or "caios-internal",
            protocol_version=action.protocol_version or "1",
            agent_id=action.agent_id,
            model_id=action.model_id,
            model_revision=action.model_revision,
            agent_attestation=action.attestation_digest,
            tool_ids=action.tool_ids,
            invariant_ids=action.invariant_ids,
            expected_gain=action.expected_gain,
            risk=action.risk,
            reversibility=action.reversibility,
            simulation_digest=simulation_digest,
            execution_digest=digest([item.as_dict() for item in action_evidence]),
            decision="PASS" if decision == "CONTINUE" else decision,
            evidence_digests=tuple(item.digest for item in action_evidence),
        )
        ok, reasons = verify_contract(self.repo_root, contract)
        return (
            contract,
            Evidence(
                kind="work-contract",
                status="PASS" if ok else "BLOCKED",
                source="autonomy/proof_work_verifier.py",
                digest=contract.contract_digest,
                details={
                    "contract": contract.as_dict(),
                    "verified": ok,
                    "reasons": reasons,
                },
            ),
        )

    def run(self) -> list[DecisionCertificate]:
        for cycle in range(1, self.max_cycles + 1):
            started = time.monotonic_ns()
            snapshot = self.snapshotter.capture()
            self.telemetry.write(
                new_event(
                    "caios.cycle.started",
                    trace_id=self.trace_id,
                    attributes={"caios.session.id": self.session_id},
                    body={"cycle": cycle, "observation_digest": snapshot["observation_digest"]},
                )
            )
            evidence: list[Evidence] = []
            session_anchor = SessionAnchor.create(
                self.session_id,
                cycle,
                snapshot["observation_digest"],
            )
            anchor_ok, anchor_reason = self.anchors.accept(session_anchor)
            evidence.append(
                Evidence(
                    kind="session-anchor",
                    status="PASS" if anchor_ok else "BLOCKED",
                    source="federation/security_primitives.py",
                    digest=session_anchor.anchor_hash,
                    details={
                        "session_id": self.session_id,
                        "epoch": cycle,
                        "state_digest": snapshot["observation_digest"],
                        "reason": anchor_reason,
                    },
                )
            )
            authority_checks = {}
            authority_pass = True
            for principal, capability in (("caios", "supervise"), ("model", "propose")):
                ok, reason = self.authority.authorize(principal, capability)
                authority_checks[f"{principal}:{capability}"] = {"authorized": ok, "reason": reason}
                authority_pass = authority_pass and ok
            evidence.append(
                Evidence(
                    kind="authority-lattice",
                    status="PASS" if authority_pass else "BLOCKED",
                    source="autonomy/authority_lattice.py",
                    digest=digest(authority_checks),
                    details={
                        "checks": authority_checks,
                        "note": "declarative authority configuration; execution delegation remains separately enforced by the runtime/tool boundary",
                    },
                )
            )
            if not authority_pass:
                cert = DecisionCertificate(
                    cycle=cycle,
                    selected_action=None,
                    decision="HALT",
                    score=0.0,
                    gaps_before={"authority": 1.0},
                    evidence=tuple(evidence),
                    reasons=("CAIOS supervisory authority is unavailable; runtime halts fail-closed",),
                    action_fingerprint=None,
                    previous_certificate_digest=(
                        digest(self.certificates[-1].as_dict()) if self.certificates else None
                    ),
                    elapsed_ms=(time.monotonic_ns() - started) // 1_000_000,
                    observation_digest=snapshot.get("observation_digest"),
                    council_digest=None,
                    session_id=self.session_id,
                    session_anchor_hash=session_anchor.anchor_hash,
                )
                self.evidence_ledger.append(cycle, evidence)
                self.certificates.append(cert)
                break

            if not anchor_ok:
                cert = DecisionCertificate(
                    cycle=cycle,
                    selected_action=None,
                    decision="HALT",
                    score=0.0,
                    gaps_before={"session": 1.0},
                    evidence=tuple(evidence),
                    reasons=(f"session anchor rejected: {anchor_reason}",),
                    action_fingerprint=None,
                    previous_certificate_digest=(
                        digest(self.certificates[-1].as_dict()) if self.certificates else None
                    ),
                    elapsed_ms=(time.monotonic_ns() - started) // 1_000_000,
                    observation_digest=snapshot.get("observation_digest"),
                    council_digest=None,
                    session_id=self.session_id,
                    session_anchor_hash=session_anchor.anchor_hash,
                )
                self.evidence_ledger.append(cycle, evidence)
                self.certificates.append(cert)
                break

            evidence.extend(self.aethel.observe(self.repo_root))
            federation_evidence = self.federation.observe(self.repo_root)
            if federation_evidence:
                evidence.append(federation_evidence)
            evidence.append(self.agents.observe(self.repo_root))
            evidence.extend(self.remote.observe(self.repo_root))
            evidence.append(self.protocols.observe(self.repo_root))
            evidence.append(self.red_team.observe(self.repo_root))
            gaps = self._gap_vector(evidence, snapshot)
            council = self.council.deliberate(gaps, evidence)
            council_evidence = Evidence(
                kind="council",
                status="PASS",
                source="autonomy/caios_council.py",
                digest=digest(council.digest_material),
                details={
                    "priority": council.priority,
                    "dissent": list(council.dissent),
                    "roles": [opinion.role for opinion in council.opinions],
                },
            )
            evidence.append(council_evidence)

            candidates = self._baseline_candidates(gaps)
            candidates.extend(self._model_candidates(snapshot, gaps))
            if self.last_model_admission:
                evidence.append(
                    Evidence(
                        kind="model-admission",
                        status="PASS" if any(
                            row["status"] in {"ATTESTED", "ADMITTED"}
                            for row in self.last_model_admission
                        ) else "BLOCKED",
                        source="autonomy/agent_attestation.py",
                        digest=digest(self.last_model_admission),
                        details={"proposals": self.last_model_admission},
                    )
                )
            provider_egress = getattr(self.proposal_provider, "last_egress", None) if self.proposal_provider else None
            if provider_egress is not None:
                evidence.append(
                    Evidence(
                        kind="model-egress",
                        status=provider_egress.status,
                        source="autonomy/egress_policy.py",
                        digest=provider_egress.digest,
                        details=provider_egress.as_dict(),
                    )
                )
            provider_errors = getattr(self.proposal_provider, "last_errors", []) if self.proposal_provider else []
            if provider_errors:
                evidence.append(
                    Evidence(
                        kind="agent-worker-failure",
                        status="FAIL",
                        source="autonomy/multi_agent_provider.py",
                        digest=digest(provider_errors),
                        details={"workers": provider_errors},
                    )
                )
            eligible_candidates = []
            circuit_events = []
            for candidate in candidates:
                allowed, reason = self.circuit.allowed(
                    snapshot["observation_digest"],
                    candidate.fingerprint,
                )
                if allowed:
                    eligible_candidates.append(candidate)
                else:
                    circuit_events.append({
                        "action_id": candidate.action_id,
                        "reason": reason,
                    })
            if circuit_events:
                evidence.append(
                    Evidence(
                        kind="circuit-breaker",
                        status="BLOCKED",
                        source="autonomy/circuit_breaker.py",
                        digest=digest(circuit_events),
                        details={"quarantined": circuit_events},
                    )
                )
            action, score, rejected = self.planner.select(
                eligible_candidates,
                self.gate,
                council.priority,
            )
            if action is not None:
                self.telemetry.write(
                    new_event(
                        "caios.route.selected",
                        trace_id=self.trace_id,
                        attributes={"caios.session.id": self.session_id},
                        body={
                            "cycle": cycle,
                            "action_id": action.action_id,
                            "score": score,
                            "intent_fingerprint": action.intent_fingerprint,
                        },
                    )
                )

            if action is not None and action.kind == "human_review":
                executable = [c for c in candidates if c.kind != "human_review" and self.gate.validate(c)[0]]
                if executable:
                    action, score, rejected = self.planner.select(executable, self.gate)

            if action is None:
                cert = DecisionCertificate(
                    cycle=cycle,
                    selected_action=None,
                    decision="HALT",
                    score=0.0,
                    gaps_before=gaps,
                    evidence=tuple(
                        evidence
                        + [
                            Evidence(
                                kind="gate",
                                status="BLOCKED",
                                source="caios-runtime",
                                digest=digest(rejected),
                                details={"rejected_candidates": rejected},
                            )
                        ]
                    ),
                    reasons=("no constitutionally viable action exists",),
                    action_fingerprint=None,
                    previous_certificate_digest=(
                        digest(self.certificates[-1].as_dict()) if self.certificates else None
                    ),
                    elapsed_ms=(time.monotonic_ns() - started) // 1_000_000,
                    observation_digest=snapshot.get("observation_digest"),
                    council_digest=digest(council.digest_material),
                    session_id=self.session_id,
                    session_anchor_hash=session_anchor.anchor_hash,
                )
                self.certificates.append(cert)
                break

            try:
                action_evidence = self._execute(action)
            except Exception as exc:
                action_evidence = [
                    Evidence(
                        kind="execution",
                        status="FAIL",
                        source="caios-runtime",
                        digest=digest(str(exc)),
                        details={"exception": type(exc).__name__, "message": str(exc)},
                    )
                ]
            decision = "CONTINUE"
            reasons = [action.rationale]
            if any(e.status in {"BLOCKED", "REQUIRED"} for e in action_evidence):
                decision = "HALT"
                reasons.append("execution requires an external or human capability")
            if any(e.kind == "test" and e.status == "FAIL" for e in action_evidence):
                decision = "CONTINUE"
                reasons.append("failed test evidence increases the verification gap; next cycle may repair")

            circuit_outcome = (
                "FAIL" if any(item.status == "FAIL" for item in action_evidence)
                else "BLOCKED" if any(
                    item.status in {"BLOCKED", "REQUIRED"}
                    for item in action_evidence
                )
                else "PASS"
            )
            circuit_record = self.circuit.record(
                snapshot["observation_digest"],
                action.fingerprint,
                circuit_outcome,
            )
            evidence.append(
                Evidence(
                    kind="circuit-breaker",
                    status="PASS" if not circuit_record.quarantined else "BLOCKED",
                    source="autonomy/circuit_breaker.py",
                    digest=digest(circuit_record.as_dict()),
                    details=circuit_record.as_dict(),
                )
            )

            if action.agent_id:
                failed = any(item.status == "FAIL" for item in action_evidence)
                blocked = any(item.status in {"BLOCKED", "REQUIRED"} for item in action_evidence)
                has_test = any(item.kind == "test" for item in action_evidence)
                test_pass = (
                    any(item.kind == "test" and item.status == "PASS" for item in action_evidence)
                    if has_test
                    else None
                )
                rollback = any(
                    item.kind == "patch"
                    and item.status == "FAIL"
                    and item.details.get("rollback_returncode") == 0
                    for item in action_evidence
                )
                self.reputation.record(
                    action.agent_id,
                    action_kind=action.kind,
                    outcome="FAIL" if failed else "BLOCKED" if blocked else "PASS",
                    test_pass=test_pass,
                    evidence_gain=action.evidence_gain,
                    risk=action.risk,
                    rollback=rollback,
                )

            contract, contract_evidence = self._build_work_contract(
                action,
                snapshot,
                action_evidence,
                decision,
            )
            evidence.append(contract_evidence)
            if contract_evidence.status != "PASS":
                decision = "HALT"
                reasons.append("work contract verification failed")

            self.evidence_ledger.append(
                cycle,
                evidence + action_evidence,
            )

            cert = DecisionCertificate(
                cycle=cycle,
                selected_action=action.action_id,
                decision=decision,
                score=score,
                gaps_before=gaps,
                evidence=tuple(evidence + action_evidence),
                reasons=tuple(reasons),
                action_fingerprint=action.fingerprint,
                previous_certificate_digest=(
                    digest(self.certificates[-1].as_dict()) if self.certificates else None
                ),
                elapsed_ms=(time.monotonic_ns() - started) // 1_000_000,
                observation_digest=snapshot.get("observation_digest"),
                council_digest=digest(council.digest_material),
                session_id=self.session_id,
                session_anchor_hash=session_anchor.anchor_hash,
                work_contract_digest=contract.contract_digest,
            )
            self.certificates.append(cert)
            self.telemetry.write(
                new_event(
                    "caios.proof.sealed",
                    trace_id=self.trace_id,
                    attributes={"caios.session.id": self.session_id},
                    body={
                        "cycle": cycle,
                        "proof_digest": cert.proof_digest,
                        "work_contract_digest": cert.work_contract_digest,
                        "decision": cert.decision,
                    },
                )
            )

            if decision == "HALT":
                break

        return self.certificates


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_certificates(certificates: list[DecisionCertificate], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for cert in certificates:
            handle.write(json.dumps(cert.as_dict(), sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAIOS autonomous proof-carrying runtime")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--max-commands", type=int, default=20)
    parser.add_argument("--config", default=None)
    parser.add_argument("--agent-config", default=None)
    parser.add_argument("--output", default="ops/caios/autonomy-certificates.jsonl")
    parser.add_argument("--session-id", default=None)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    provider = None
    direct_endpoint_requested = bool(
        os.getenv("CAIOS_MODEL_URL") or os.getenv("CAIOS_MODEL_NAME")
    )
    if direct_endpoint_requested:
        print(json.dumps({
            "provider_activation": "BLOCKED",
            "reason": (
                "direct endpoint environment activation is disabled; "
                "use a registry-bound --agent-config"
            ),
        }, sort_keys=True), file=sys.stderr)
        return 2

    raw_config_path = args.agent_config if args.agent_config else args.config
    config_path = Path(raw_config_path) if raw_config_path else None
    if config_path is not None:
        if not config_path.is_absolute():
            config_path = repo_root / config_path
        try:
            # This preflights the exact destination, agent, protocol, model,
            # source binding and approval record before a provider can be called.
            from autonomy.patch_proposal import load_provider
            provider = load_provider(
                repo_root,
                config_path,
                require_source_context=False,
            )
        except Exception as exc:
            print(json.dumps({
                "provider_activation": "BLOCKED",
                "reason": f"{type(exc).__name__}:{str(exc)[:1000]}",
            }, sort_keys=True), file=sys.stderr)
            return 2

    runtime = AutonomousRuntime(
        repo_root=repo_root,
        proposal_provider=provider,
        max_cycles=args.cycles,
        max_commands=args.max_commands,
    )
    if args.session_id:
        runtime.session_id = str(args.session_id)
    certificates = runtime.run()
    write_certificates(certificates, repo_root / args.output)

    print(json.dumps([c.as_dict() for c in certificates], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
from pathlib import Path
from typing import Any, Iterable

from autonomy.agent_router import AgentRegistry
from autonomy.caios_council import CAIOSCouncil
from conformance.contract import inspect_contract


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


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

    @property
    def fingerprint(self) -> str:
        return digest(dataclasses.asdict(self))


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


class OpenAICompatibleProposalProvider:
    """
    Optional model adapter.

    The endpoint is expected to return a JSON object:
      {"proposals": [{"kind": "...", "target": "...", ...}]}

    The runtime never executes raw model text. Only schema-valid proposal
    objects reach the deterministic policy gate.
    """

    def __init__(self, endpoint: str, model: str, api_key: str | None = None) -> None:
        parsed = urllib.parse.urlparse(endpoint)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("model endpoint must be an absolute HTTP(S) URL")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("non-local model endpoints must use HTTPS")
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key

    def propose(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return JSON only. You are a proposal engine, not an execution authority. "
                        "Generate small, reversible, evidence-producing actions. Never claim a test passed "
                        "without evidence. Never request arbitrary shell access."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(snapshot, sort_keys=True),
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
        with urllib.request.urlopen(req, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        if "proposals" in data:
            return list(data["proposals"])
        if "choices" in data:
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return list(parsed.get("proposals", []))
        return []


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

    def __init__(self, repo_root: Path, max_patch_lines: int = 250) -> None:
        self.repo_root = repo_root.resolve()
        self.max_patch_lines = max_patch_lines

    def validate(self, action: CandidateAction) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if action.kind not in self.ALLOWED_KINDS:
            reasons.append(f"action kind '{action.kind}' is not in the allowlist")

        numeric_fields = {
            "expected_gain": action.expected_gain,
            "risk": action.risk,
            "reversibility": action.reversibility,
            "resource_cost": action.resource_cost,
            "evidence_gain": action.evidence_gain,
        }
        for field, value in numeric_fields.items():
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                reasons.append(f"{field} must be finite and within [0,1]")

        target = (self.repo_root / action.target).resolve()
        try:
            target.relative_to(self.repo_root)
        except ValueError:
            reasons.append("target escapes repository root")

        if action.risk > 0.85:
            reasons.append("risk exceeds autonomous threshold")
        if action.reversibility < 0.40 and action.kind != "human_review":
            reasons.append("action is insufficiently reversible")
        if action.kind in {"run_test", "run_security_scan"} and action.action_id.startswith("model-"):
            reasons.append("model-originated actions cannot supply arbitrary executable commands")

        if action.kind == "apply_patch":
            if not action.unified_diff:
                reasons.append("patch action has no unified diff")
            changed_lines = sum(
                1 for line in action.unified_diff.splitlines()
                if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
            )
            if changed_lines > self.max_patch_lines:
                reasons.append("patch exceeds maximum autonomous change budget")
            for line in action.unified_diff.splitlines():
                if line.startswith(("+++ ", "--- ")):
                    patch_path = line[4:].split("\t", 1)[0]
                    if patch_path == "/dev/null":
                        if line.startswith("+++ "):
                            reasons.append("autonomous patch deletion is not permitted")
                        continue
                    normalized = patch_path[2:] if patch_path.startswith(("a/", "b/")) else patch_path
                    if normalized.startswith(("/", "../")) or "/../" in normalized or normalized.startswith(".git/"):
                        reasons.append("patch path escapes or targets git internals")

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


class AgentObserver:
    """Reports which registered agent families are eligible for the cycle."""

    def observe(self, repo_root: Path, risk: float = 0.60) -> Evidence:
        try:
            registry = AgentRegistry(repo_root)
            capabilities = ("coding", "testing", "patching") if risk >= 0.55 else ("planning", "reasoning")
            plan = registry.plan_quorum(
                capabilities,
                ("acp", "mcp", "openai-compatible"),
                risk,
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
        proposal_provider: OpenAICompatibleProposalProvider | None = None,
        max_cycles: int = 5,
        max_commands: int = 20,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.runner = command_runner or SafeCommandRunner(self.repo_root)
        self.snapshotter = RepositorySnapshot(self.runner)
        self.aethel = AethelObserver()
        self.federation = FederationObserver()
        self.council = CAIOSCouncil()
        self.gate = ConstitutionalGate(self.repo_root)
        self.planner = ViabilityPlanner()
        self.proposal_provider = proposal_provider
        self.max_cycles = max_cycles
        self.max_commands = max_commands
        self.commands_used = 0
        self.certificates: list[DecisionCertificate] = []

    def _gap_vector(self, evidence: list[Evidence], snapshot: dict[str, Any]) -> dict[str, float]:
        gaps = {
            "conformance": 0.0,
            "verification": 0.0,
            "integration": 0.0,
            "security": 0.0,
            "working_tree": 0.0,
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
        return gaps

    def _baseline_candidates(self, gaps: dict[str, float]) -> list[CandidateAction]:
        candidates: list[CandidateAction] = []
        if gaps["verification"]:
            test_command = (
                ("python", "-m", "pytest", "-q", "interop")
                if (self.repo_root / "interop").exists()
                else ("python", "-m", "pytest", "-q")
            )
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

    def _model_candidates(self, snapshot: dict[str, Any], gaps: dict[str, float]) -> list[CandidateAction]:
        if not self.proposal_provider:
            return []
        try:
            raw = self.proposal_provider.propose({"snapshot": snapshot, "gaps": gaps})
        except Exception:
            return []
        candidates: list[CandidateAction] = []
        for idx, item in enumerate(raw[:20]):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "human_review"))
            target = str(item.get("target", "."))
            diff = str(item.get("unified_diff", ""))
            command = tuple(shlex.split(str(item["command"]))) if item.get("command") else ()
            try:
                metrics = {
                    "expected_gain": float(item.get("expected_gain", 0.30)),
                    "risk": float(item.get("risk", 0.50)),
                    "reversibility": float(item.get("reversibility", 0.60)),
                    "resource_cost": float(item.get("resource_cost", 0.30)),
                    "evidence_gain": float(item.get("evidence_gain", 0.50)),
                }
            except (TypeError, ValueError):
                continue
            if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in metrics.values()):
                continue
            candidates.append(
                CandidateAction(
                    action_id=f"model-{idx}-{str(item.get('action_id', 'proposal'))}",
                    kind=kind,
                    target=target,
                    rationale=str(item.get("rationale", "model proposal")),
                    expected_gain=metrics["expected_gain"],
                    risk=metrics["risk"],
                    reversibility=metrics["reversibility"],
                    resource_cost=metrics["resource_cost"],
                    evidence_gain=metrics["evidence_gain"],
                    command=command,
                    unified_diff=diff,
                )
            )
        return candidates

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

    def run(self) -> list[DecisionCertificate]:
        for cycle in range(1, self.max_cycles + 1):
            started = time.monotonic_ns()
            snapshot = self.snapshotter.capture()
            evidence = self.aethel.observe(self.repo_root)
            federation_evidence = self.federation.observe(self.repo_root)
            if federation_evidence:
                evidence.append(federation_evidence)
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
            action, score, rejected = self.planner.select(candidates, self.gate, council.priority)

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
            )
            self.certificates.append(cert)

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
    parser.add_argument("--output", default="ops/caios/autonomy-certificates.jsonl")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    provider = None
    if os.getenv("CAIOS_MODEL_URL") and os.getenv("CAIOS_MODEL_NAME"):
        provider = OpenAICompatibleProposalProvider(
            endpoint=os.environ["CAIOS_MODEL_URL"],
            model=os.environ["CAIOS_MODEL_NAME"],
            api_key=os.getenv("CAIOS_MODEL_API_KEY"),
        )

    if args.config:
        config = load_json(Path(args.config))
        model_cfg = config.get("model", {})
        if model_cfg.get("endpoint") and model_cfg.get("model"):
            provider = OpenAICompatibleProposalProvider(
                endpoint=str(model_cfg["endpoint"]),
                model=str(model_cfg["model"]),
                api_key=str(model_cfg.get("api_key")) if model_cfg.get("api_key") else None,
            )

    runtime = AutonomousRuntime(
        repo_root=repo_root,
        proposal_provider=provider,
        max_cycles=args.cycles,
        max_commands=args.max_commands,
    )
    certificates = runtime.run()
    write_certificates(certificates, repo_root / args.output)

    print(json.dumps([c.as_dict() for c in certificates], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

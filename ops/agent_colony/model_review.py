#!/usr/bin/env python3
"""Opt-in, metadata-only model collaboration for the AETHEL engineering colony.

This adapter reuses CAIOS endpoint admission and proposal transport. It never
executes model output, never provides source-code context, and is disabled unless
both an explicit CLI flag and an environment kill-switch are set.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autonomy.patch_proposal import load_endpoint_bindings, load_provider
from ops.agent_colony.collaboration import ROLE_TASKS, build_role_task_contexts

CONFIG_SCHEMA = "caios-agent-endpoints/v1"
REQUIRED_REVIEW_ROLES = (
    "protocol_analyst",
    "security_analyst",
    "devops_qa",
    "toolbox_architect",
)
REQUIRED_AGENT_FIELDS = (
    "endpoint_id",
    "agent_id",
    "endpoint",
    "model",
    "model_revision",
    "protocol",
    "protocol_version",
    "agent_version",
    "source_ref",
    "role_id",
)
METADATA_FIELDS = ("id", "severity", "title", "evidence_path", "status")
OUTPUT_TEXT_FIELDS = {
    "kind": 100,
    "target": 300,
    "title": 300,
    "summary": 1000,
    "rationale": 1200,
    "recommendation": 1200,
}
SECRET_PATTERNS = (
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(api[_ -]?key|access[_ -]?token|secret|password)\s*[:=]\s*[^\s,;]+"),
)


def _inside_root(root: Path, path: str | Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must remain inside the repository root") from exc
    return resolved


def _read_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} is not a file")
    if path.stat().st_size > 2_000_000:
        raise ValueError(f"{label} exceeds the 2 MB limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _valid_env_name(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"CAIOS_[A-Z0-9_]+_API_KEY", value))


def validate_model_review_config(
    repo_root: Path,
    config_path: str | Path = "autonomy/agent_endpoints.json",
    manifest_path: str | Path = "ops/agent_colony/manifest.json",
) -> dict[str, Any]:
    """Validate role coverage and exact endpoint pins without calling a model.

    Full CAIOS agent/model/protocol admission is repeated by load_provider at
    execution time. This preflight intentionally does not require credentials.
    """
    root = Path(repo_root).resolve()
    config_file = _inside_root(root, config_path, "model review config")
    manifest_file = _inside_root(root, manifest_path, "colony manifest")

    if not config_file.is_file():
        return {
            "status": "DISABLED",
            "reason": "autonomy/agent_endpoints.json is absent; no model providers are configured",
            "config_path": str(config_file.relative_to(root)),
            "external_model_calls_attempted": False,
            "full_agent_model_protocol_admission_performed": False,
        }

    raw = _read_object(config_file, "model review config")
    if raw.get("schema") != CONFIG_SCHEMA or not isinstance(raw.get("agents"), list):
        raise ValueError("model review config must use caios-agent-endpoints/v1 with an agents list")
    entries = raw["agents"]
    if len(entries) != len(REQUIRED_REVIEW_ROLES):
        raise ValueError("model review config must bind exactly one provider to each of the four S1 review roles")

    bindings = load_endpoint_bindings(root)
    seen_agents: set[str] = set()
    seen_endpoints: set[str] = set()
    seen_roles: set[str] = set()
    agent_bindings: dict[str, str] = {}
    approvals = []

    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            raise ValueError(f"model review entry {index} must be an object")
        missing = [
            key for key in REQUIRED_AGENT_FIELDS
            if not isinstance(item.get(key), str) or not item[key].strip()
        ]
        if missing:
            raise ValueError(f"model review entry {index} missing required fields: {','.join(missing)}")
        endpoint_id = item["endpoint_id"]
        agent_id = item["agent_id"]
        role_id = item["role_id"]
        if role_id not in REQUIRED_REVIEW_ROLES or role_id not in ROLE_TASKS:
            raise ValueError(f"model review role is not allowed: {role_id}")
        if endpoint_id in seen_endpoints:
            raise ValueError(f"duplicate provider endpoint ID: {endpoint_id}")
        if agent_id in seen_agents:
            raise ValueError(f"duplicate provider agent ID: {agent_id}")
        if role_id in seen_roles:
            raise ValueError(f"duplicate S1 role binding: {role_id}")
        seen_endpoints.add(endpoint_id)
        seen_agents.add(agent_id)
        seen_roles.add(role_id)

        if "api_key_env" not in item:
            raise ValueError(f"model review entry {index} must explicitly declare api_key_env (string or null)")
        api_key_env = item["api_key_env"]
        if api_key_env is not None and not _valid_env_name(api_key_env):
            raise ValueError(f"model review entry {index} api_key_env must use CAIOS_*_API_KEY or null")
        if item.get("send_source_context", False) is not False:
            raise ValueError("model review agents must set send_source_context=false; only bounded evidence metadata may be sent")

        binding = bindings.get(endpoint_id)
        if binding is None:
            raise ValueError(f"provider endpoint is not registered: {endpoint_id}")
        exact_values = {
            "endpoint_url": item["endpoint"],
            "agent_id": agent_id,
            "agent_version": item["agent_version"],
            "source_ref": item["source_ref"],
            "protocol": item["protocol"],
            "protocol_version": item["protocol_version"],
            "model_id": item["model"],
            "model_revision": item["model_revision"],
            "api_key_env": api_key_env,
        }
        for key, actual in exact_values.items():
            if binding.get(key) != actual:
                raise ValueError(f"provider endpoint pin mismatch: {endpoint_id}:{key}")
        approval_ref = binding.get("approval_ref")
        if not isinstance(approval_ref, str) or not approval_ref.startswith("https://"):
            raise ValueError(f"provider endpoint lacks an HTTPS approval reference: {endpoint_id}")

        agent_bindings[agent_id] = role_id
        approvals.append({
            "endpoint_id": endpoint_id,
            "role_id": role_id,
            "approval_ref": approval_ref,
        })

    if set(seen_roles) != set(REQUIRED_REVIEW_ROLES):
        missing_roles = sorted(set(REQUIRED_REVIEW_ROLES) - seen_roles)
        raise ValueError("model review role coverage incomplete: " + ",".join(missing_roles))

    manifest = _read_object(manifest_file, "colony manifest")
    # Validate manifest role/toolbox references before any model configuration is used.
    build_role_task_contexts(
        manifest,
        agent_bindings=agent_bindings,
        source_revision="0" * 40,
        findings=[],
    )

    return {
        "status": "PINNED_CONFIG_READY",
        "config_path": str(config_file.relative_to(root)),
        "provider_count": len(entries),
        "roles": list(REQUIRED_REVIEW_ROLES),
        "endpoint_approvals": approvals,
        "source_context_sent": False,
        "external_model_calls_attempted": False,
        "full_agent_model_protocol_admission_performed": False,
        "note": "Full CAIOS agent, model, protocol, source-identity and credential admission runs again before an explicit model call.",
    }


def _metadata_findings(findings: Any) -> list[dict[str, str]]:
    if not isinstance(findings, list):
        raise ValueError("findings must be a list")
    clean: list[dict[str, str]] = []
    for item in findings[:100]:
        if not isinstance(item, dict):
            continue
        row = {}
        for key in METADATA_FIELDS:
            value = item.get(key)
            if isinstance(value, str):
                row[key] = value[:300]
        if row:
            clean.append(row)
    return clean


def _scrub_text(value: str, limit: int) -> str:
    text = value[:limit]
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _summarize_proposals(proposals: Any) -> list[dict[str, Any]]:
    """Return bounded, non-executable review summaries; deliberately drop commands and diffs."""
    if not isinstance(proposals, list):
        return []
    output = []
    for item in proposals[:100]:
        if not isinstance(item, dict):
            continue
        row: dict[str, Any] = {"trust": "UNTRUSTED_MODEL_PROPOSAL"}
        agent_id = item.get("agent_id")
        if isinstance(agent_id, str):
            row["agent_id"] = agent_id[:160]
        for key, limit in OUTPUT_TEXT_FIELDS.items():
            value = item.get(key)
            if isinstance(value, str):
                row[key] = _scrub_text(value, limit)
        risk = item.get("risk")
        if isinstance(risk, (int, float)) and not isinstance(risk, bool) and 0 <= risk <= 1:
            row["risk"] = float(risk)
        output.append(row)
    return output


def run_model_review(
    repo_root: Path,
    *,
    config_path: str | Path = "autonomy/agent_endpoints.json",
    manifest_path: str | Path = "ops/agent_colony/manifest.json",
    findings: list[dict[str, Any]] | None = None,
    source_revision: str | None = None,
    execute: bool = False,
    provider_loader: Callable[[Path, Path], Any] | None = None,
) -> dict[str, Any]:
    """Preflight by default; execute four read-only proposal agents only with double opt-in."""
    root = Path(repo_root).resolve()
    config_file = _inside_root(root, config_path, "model review config")
    manifest_file = _inside_root(root, manifest_path, "colony manifest")
    preflight = validate_model_review_config(root, config_file, manifest_file)
    if preflight["status"] == "DISABLED":
        return preflight
    if not execute:
        return {
            **preflight,
            "status": "READY_FOR_OPERATOR_REVIEW",
            "model_calls_attempted": False,
            "next_action": "Review endpoint approvals and full CAIOS admission; use --execute-model-calls plus CAIOS_ENABLE_MODEL_COLLABORATION=1 only when approved.",
        }
    if os.environ.get("CAIOS_ENABLE_MODEL_COLLABORATION") != "1":
        return {
            **preflight,
            "status": "BLOCKED",
            "reason": "explicit kill-switch not enabled; set CAIOS_ENABLE_MODEL_COLLABORATION=1 and pass --execute-model-calls",
            "model_calls_attempted": False,
        }
    if not isinstance(source_revision, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", source_revision):
        return {
            **preflight,
            "status": "BLOCKED",
            "reason": "execution requires a 40-character source commit SHA from the evidence report",
            "model_calls_attempted": False,
        }

    clean_findings = _metadata_findings(findings or [])
    manifest = _read_object(manifest_file, "colony manifest")
    config = _read_object(config_file, "model review config")
    agent_bindings = {item["agent_id"]: item["role_id"] for item in config["agents"]}
    contexts = build_role_task_contexts(
        manifest,
        agent_bindings=agent_bindings,
        source_revision=source_revision.lower(),
        findings=clean_findings,
    )
    snapshot = {
        "schema": "aethel-colony-evidence/v1",
        "source_revision": source_revision.lower(),
        "evidence_mode": "metadata-only",
        "finding_count": len(clean_findings),
        "findings": clean_findings,
        "source_code_included": False,
        "secret_values_included": False,
        "tool_execution_authority": False,
    }

    # Full provider admission and API-key lookup occur only after both explicit gates.
    if provider_loader is None:
        provider = load_provider(root, config_file, require_source_context=False)
    else:
        provider = provider_loader(root, config_file)

    try:
        proposals = provider.propose(snapshot, task_contexts=contexts)
        provider_errors = getattr(provider, "last_errors", [])
    except Exception as exc:
        return {
            **preflight,
            "status": "FAILED_CLOSED",
            "reason": "provider call failed: " + type(exc).__name__,
            "model_calls_attempted": True,
            "source_revision": source_revision.lower(),
            "release_decision": "HOLD",
            "code_changes_created": False,
            "tool_calls_executed": False,
        }

    summarized = _summarize_proposals(proposals)
    expected_agents = set(agent_bindings)
    responding_agents = {item.get("agent_id") for item in summarized if isinstance(item.get("agent_id"), str)}
    missing_agents = sorted(expected_agents - responding_agents)
    sanitized_errors = []
    for error in provider_errors if isinstance(provider_errors, list) else []:
        if isinstance(error, dict):
            sanitized_errors.append({
                "agent_id": str(error.get("agent_id", ""))[:160],
                "error_type": str(error.get("error_type", "ProviderError"))[:120],
            })
    status = "PROPOSALS_ONLY" if not sanitized_errors and not missing_agents else "PARTIAL"
    return {
        **preflight,
        "status": status,
        "model_calls_attempted": True,
        "source_revision": source_revision.lower(),
        "input_finding_count": len(clean_findings),
        "responding_agents": sorted(responding_agents),
        "missing_agents": missing_agents,
        "provider_errors": sanitized_errors,
        "proposals": summarized,
        "release_decision": "HOLD",
        "code_changes_created": False,
        "tool_calls_executed": False,
        "human_review_required": True,
    }


def _load_evidence_report(path: Path) -> tuple[str, list[dict[str, Any]]]:
    report = _read_object(path, "evidence report")
    revision = report.get("source_head_sha") or report.get("source_revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise ValueError("evidence report must contain source_head_sha or source_revision as a commit SHA")
    findings = report.get("findings")
    if findings is None and isinstance(report.get("evidence"), dict):
        findings = report["evidence"].get("findings")
    if findings is None:
        findings = []
    if not isinstance(findings, list):
        raise ValueError("evidence report findings must be a list")
    return revision, findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="preflight or run metadata-only CAIOS colony reviewers")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--config", default="autonomy/agent_endpoints.json")
    parser.add_argument("--manifest", default="ops/agent_colony/manifest.json")
    parser.add_argument("--evidence-report", default=None)
    parser.add_argument("--execute-model-calls", action="store_true")
    parser.add_argument("--output", default="/tmp/aethel-colony-model-review.json")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    try:
        findings = []
        revision = None
        if args.execute_model_calls:
            if not args.evidence_report:
                raise ValueError("--evidence-report is required when --execute-model-calls is used")
            evidence_path = Path(args.evidence_report).resolve()
            revision, findings = _load_evidence_report(evidence_path)
        result = run_model_review(
            root,
            config_path=args.config,
            manifest_path=args.manifest,
            findings=findings,
            source_revision=revision,
            execute=args.execute_model_calls,
        )
    except Exception as exc:
        result = {
            "status": "BLOCKED",
            "reason": type(exc).__name__ + ": " + _scrub_text(str(exc), 500),
            "model_calls_attempted": False,
        }

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"DISABLED", "READY_FOR_OPERATOR_REVIEW", "PROPOSALS_ONLY", "PARTIAL"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

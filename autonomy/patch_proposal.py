#!/usr/bin/env python3
"""
CAIOS proposal-only patch planner.

Queries registered proposal agents and emits at most one low-risk patch artifact.
It NEVER applies the proposed patch or executes proposed code. A separate,
secret-free validation job must revalidate and test the artifact before a
publisher with repository write permission may create a pull request.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

from autonomy.agent_attestation import validate_agent_source_binding, validate_proposal
from autonomy.agent_router import AgentRegistry
from autonomy.context_window import ContextWindow
from autonomy.caios_runtime import CandidateAction, ConstitutionalGate, ViabilityPlanner, digest, _normalize_string_list
from autonomy.multi_agent_provider import EndpointSpec, MultiAgentProposalProvider
from autonomy.model_admission import ModelRegistry
from autonomy.protocol_admission import ProtocolRegistry
from conformance.contract import inspect_contract

SCHEMA = "caios-patch-proposal/v1"
MAX_PATCH_BYTES = 50_000
ABSOLUTE_RISK_CEILING = 0.55
ENDPOINT_REGISTRY_SCHEMA = "caios-provider-endpoints/v1"


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ("git", *args),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr[-1000:]}")
    return proc.stdout.strip()


def _validate_endpoint_url(endpoint_url: str) -> None:
    parsed = urllib.parse.urlsplit(endpoint_url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("provider endpoint must be an absolute HTTP(S) URL")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("non-local provider endpoints must use HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("provider endpoint must not include credentials, query parameters, or a fragment")


def load_endpoint_bindings(repo_root: Path) -> dict[str, dict[str, str]]:
    path = repo_root / "autonomy" / "provider_endpoint_registry.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"provider-endpoint-registry-unavailable:{type(exc).__name__}") from exc

    if not isinstance(raw, dict) or raw.get("schema") != ENDPOINT_REGISTRY_SCHEMA:
        raise ValueError("provider-endpoint-registry-schema-invalid")
    policy = raw.get("policy")
    endpoints = raw.get("endpoints")
    if not isinstance(policy, dict) or policy.get("unknown_endpoint") != "REJECT":
        raise ValueError("provider-endpoint-registry-policy-invalid")
    if policy.get("exact_url_match") is not True or policy.get("exact_agent_model_protocol_match") is not True:
        raise ValueError("provider-endpoint-registry-must-require-exact-matches")
    if policy.get("require_approval_ref") is not True:
        raise ValueError("provider-endpoint-registry-must-require-approval-reference")
    if not isinstance(endpoints, list):
        raise ValueError("provider-endpoint-registry-endpoints-must-be-a-list")

    required_fields = (
        "id", "endpoint_url", "agent_id", "agent_version", "source_ref",
        "protocol", "protocol_version", "model_id", "model_revision", "approval_ref",
    )
    bindings: dict[str, dict[str, Any]] = {}
    for index, endpoint in enumerate(endpoints):
        if not isinstance(endpoint, dict):
            raise ValueError(f"provider-endpoint-entry-{index}-must-be-an-object")
        missing = [
            key for key in required_fields
            if not isinstance(endpoint.get(key), str) or not endpoint[key].strip()
        ]
        if "api_key_env" not in endpoint:
            missing.append("api_key_env")
        if missing:
            raise ValueError(
                f"provider-endpoint-entry-{index}-missing-fields:{','.join(missing)}"
            )
        endpoint_api_key_env = endpoint["api_key_env"]
        if endpoint_api_key_env is not None and (
            not isinstance(endpoint_api_key_env, str)
            or not endpoint_api_key_env.startswith("CAIOS_")
            or not endpoint_api_key_env.endswith("_API_KEY")
        ):
            raise ValueError(f"provider-endpoint-api-key-environment-invalid:{endpoint.get('id', index)}")
        endpoint_id = endpoint["id"]
        if endpoint_id in bindings:
            raise ValueError(f"provider-endpoint-id-duplicate:{endpoint_id}")
        _validate_endpoint_url(endpoint["endpoint_url"])
        bindings[endpoint_id] = {key: endpoint[key] for key in required_fields}
        bindings[endpoint_id]["api_key_env"] = endpoint_api_key_env
    return bindings


def load_provider(
    repo_root: Path,
    config_path: Path,
    *,
    require_source_context: bool = True,
) -> MultiAgentProposalProvider:
    repo_root = repo_root.resolve()
    config_path = config_path.resolve()
    try:
        config_path.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("agent configuration must remain inside the repository") from exc
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if (
        not isinstance(raw, dict)
        or raw.get("schema") != "caios-agent-endpoints/v1"
        or not isinstance(raw.get("agents"), list)
        or not raw["agents"]
    ):
        raise ValueError("agent configuration must use caios-agent-endpoints/v1 and contain a non-empty agents list")
    endpoint_bindings = load_endpoint_bindings(repo_root)

    specs = []
    for index, item in enumerate(raw["agents"]):
        if not isinstance(item, dict):
            raise ValueError(f"agent entry {index} must be an object")
        required = (
            "endpoint_id", "agent_id", "endpoint", "model", "model_revision",
            "protocol", "protocol_version", "agent_version", "source_ref",
        )
        missing = [key for key in required if not isinstance(item.get(key), str) or not item[key].strip()]
        if missing:
            raise ValueError(f"agent entry {index} missing required fields: {','.join(missing)}")

        # Reject unpinned destinations and identity mismatches before any
        # source context is constructed or sent to the configured endpoint.
        endpoint_id = item["endpoint_id"]
        binding = endpoint_bindings.get(endpoint_id)
        if binding is None:
            raise ValueError(f"provider-endpoint-not-registered:{endpoint_id}")
        _validate_endpoint_url(item["endpoint"])
        api_key_env = item.get("api_key_env")
        if api_key_env is not None and (not isinstance(api_key_env, str) or not api_key_env.strip()):
            raise ValueError(f"agent entry {index} api_key_env must be a non-empty string")
        if api_key_env and (not api_key_env.startswith("CAIOS_") or not api_key_env.endswith("_API_KEY")):
            raise ValueError(f"agent entry {index} api_key_env must use an approved CAIOS_*_API_KEY name")
        if api_key_env and not os.environ.get(api_key_env):
            raise ValueError(f"configured API key environment variable is unset: {api_key_env}")
        config_to_binding = {
            "endpoint_url": item["endpoint"],
            "agent_id": item["agent_id"],
            "agent_version": item["agent_version"],
            "source_ref": item["source_ref"],
            "protocol": item["protocol"],
            "protocol_version": item["protocol_version"],
            "model_id": item["model"],
            "model_revision": item["model_revision"],
            "api_key_env": api_key_env,
        }
        for binding_key, configured_value in config_to_binding.items():
            if binding[binding_key] != configured_value:
                raise ValueError(
                    f"provider-endpoint-binding-mismatch:{endpoint_id}:{binding_key}"
                )
        source_context_opt_in = item.get("send_source_context", False)
        if not isinstance(source_context_opt_in, bool):
            raise ValueError(f"agent entry {index} send_source_context must be a JSON boolean")

        specs.append(
            EndpointSpec(
                agent_id=item["agent_id"],
                endpoint=item["endpoint"],
                model=item["model"],
                protocol=item["protocol"],
                agent_version=item["agent_version"],
                source_ref=item["source_ref"],
                model_revision=item["model_revision"],
                protocol_version=item["protocol_version"],
                api_key=os.environ.get(api_key_env) if api_key_env else None,
                max_proposals=max(1, min(int(item.get("max_proposals", 8)), 20)),
                send_source_context=source_context_opt_in,
            )
        )

    if require_source_context and not any(spec.send_source_context for spec in specs):
        raise ValueError(
            "at least one registered agent must explicitly enable send_source_context for patch planning"
        )

    # Complete all repository-owned identity, protocol, capability, and model
    # admission checks before returning a provider that can send source context.
    # A configuration entry is never allowed to establish its own authority.
    try:
        agent_registry = AgentRegistry(repo_root)
        model_registry = ModelRegistry(repo_root)
        protocol_registry = ProtocolRegistry(repo_root)
    except Exception as exc:
        raise ValueError(f"proposal admission registries unavailable: {type(exc).__name__}") from exc

    minimum_provenance = float(
        agent_registry.policy.get("minimum_provenance_confidence", 0.90)
    )
    for spec in specs:
        profile = agent_registry.agents.get(spec.agent_id)
        if profile is None:
            raise ValueError(f"agent-id-not-registered:{spec.agent_id}")
        if profile.authority != "proposal":
            raise ValueError(f"agent-is-not-proposal-authority:{spec.agent_id}")
        if profile.provenance_confidence < minimum_provenance:
            raise ValueError(f"agent-provenance-confidence-below-floor:{spec.agent_id}")

        source_binding_reasons = validate_agent_source_binding(
            repo_root,
            profile,
            agent_version=spec.agent_version,
            source_ref=spec.source_ref,
        )
        if source_binding_reasons:
            raise ValueError(
                f"agent-identity-binding-failed:{spec.agent_id}:"
                + ",".join(source_binding_reasons)
            )
        if not {"coding", "patching"}.issubset(profile.capabilities):
            raise ValueError(f"agent-lacks-coding-or-patching-capability:{spec.agent_id}")
        if spec.protocol not in profile.protocols:
            raise ValueError(f"agent-protocol-not-registered:{spec.agent_id}:{spec.protocol}")
        expected_protocol_version = profile.protocol_versions.get(spec.protocol)
        if not expected_protocol_version:
            raise ValueError(f"agent-protocol-version-not-pinned:{spec.agent_id}:{spec.protocol}")
        if spec.protocol_version != expected_protocol_version:
            raise ValueError(f"agent-protocol-version-mismatch:{spec.agent_id}:{spec.protocol}")
        protocol_ok, protocol_reasons = protocol_registry.admit(
            spec.protocol, spec.protocol_version, allow_draft=False
        )
        if not protocol_ok:
            raise ValueError(
                f"protocol-not-admitted:{spec.protocol}:{spec.protocol_version}:"
                + ",".join(protocol_reasons)
            )
        protocol_profile = protocol_registry.get(spec.protocol)
        if protocol_profile is None:
            raise ValueError(f"protocol-not-registered:{spec.protocol}")
        if protocol_profile.role == "model-proposal-transport":
            if profile.agent_kind != "model-proposal-adapter":
                raise ValueError(
                    f"model-proposal-transport-requires-adapter-identity:{spec.agent_id}"
                )
            if profile.external_tool_execution is not False:
                raise ValueError(
                    f"model-proposal-adapter-must-not-execute-external-tools:{spec.agent_id}"
                )
        elif profile.agent_kind == "model-proposal-adapter":
            raise ValueError(
                f"model-proposal-adapter-cannot-claim-agent-execution-protocol:{spec.protocol}"
            )
        model_ok, model_reasons = model_registry.admit(
            spec.model, model_revision=spec.model_revision or None
        )
        if not model_ok:
            raise ValueError(
                f"model-not-admitted:{spec.model}:" + ",".join(model_reasons)
            )
    return MultiAgentProposalProvider(tuple(specs))


def _unit_interval_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number within [0,1]")
    if isinstance(value, int):
        # Bound before float conversion so arbitrarily large integers cannot overflow.
        if value < 0 or value > 1:
            raise ValueError(f"{field} must be a finite number within [0,1]")
        return float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{field} must be a finite number within [0,1]")
    return value


def _number(item: dict[str, Any], key: str, default: float) -> float:
    return _unit_interval_number(item.get(key, default), key)


def select_candidate(
    repo_root: Path,
    base_sha: str,
    proposals: list[dict[str, Any]],
    *,
    max_risk: float,
    max_proposals: int = 20,
) -> dict[str, Any]:
    max_risk_value = _unit_interval_number(max_risk, "max_risk")
    registry = AgentRegistry(repo_root)
    policy_risk = _unit_interval_number(
        registry.policy.get("high_risk_threshold", ABSOLUTE_RISK_CEILING),
        "registered high_risk_threshold",
    )
    risk_ceiling = min(max_risk_value, policy_risk, ABSOLUTE_RISK_CEILING)
    gate = ConstitutionalGate(repo_root)
    planner = ViabilityPlanner()
    eligible: list[tuple[float, str, dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []

    for index, item in enumerate(proposals[:max_proposals]):
        if not isinstance(item, dict):
            rejected.append({"index": index, "reasons": ["proposal-not-object"]})
            continue
        if item.get("kind") != "apply_patch":
            rejected.append({"index": index, "reasons": ["only-apply_patch proposals are eligible"]})
            continue

        patch = item.get("unified_diff")
        if not isinstance(patch, str) or not patch.strip():
            rejected.append({"index": index, "reasons": ["unified-diff-missing"]})
            continue
        if len(patch.encode("utf-8")) > MAX_PATCH_BYTES:
            rejected.append({"index": index, "reasons": ["patch-exceeds-byte-budget"]})
            continue
        if "diff --git " not in patch or "\n--- " not in patch or "\n+++ " not in patch:
            rejected.append({"index": index, "reasons": ["unified-diff-malformed"]})
            continue

        try:
            metrics = {
                "expected_gain": _number(item, "expected_gain", 0.30),
                "risk": _number(item, "risk", 0.50),
                "reversibility": _number(item, "reversibility", 0.60),
                "resource_cost": _number(item, "resource_cost", 0.30),
                "evidence_gain": _number(item, "evidence_gain", 0.50),
            }
        except (TypeError, ValueError, OverflowError) as exc:
            rejected.append({"index": index, "reasons": [f"invalid-metric:{exc}"]})
            continue

        if metrics["risk"] >= risk_ceiling:
            rejected.append({
                "index": index,
                "reasons": [f"risk-not-below-autonomous-ceiling:{risk_ceiling}"],
            })
            continue

        target = item.get("target", ".")
        rationale = item.get("rationale", "registered agent patch proposal")
        invariant_ids = _normalize_string_list(item.get("invariant_ids", []))
        requested_tool_ids = _normalize_string_list(item.get("tool_ids", []))
        if not isinstance(target, str) or not target:
            rejected.append({"index": index, "reasons": ["target-must-be-non-empty-string"]})
            continue
        if not isinstance(rationale, str):
            rejected.append({"index": index, "reasons": ["rationale-must-be-string"]})
            continue
        if invariant_ids is None:
            rejected.append({"index": index, "reasons": ["invariant-ids-must-be-string-array"]})
            continue
        if requested_tool_ids is None:
            rejected.append({"index": index, "reasons": ["tool-ids-must-be-string-array"]})
            continue

        # The proposal is untrusted; canonical hashing must not be allowed to
        # turn malformed or oversized numeric values into an uncaught exception.
        try:
            proposal_digest = digest(item)
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            rejected.append({
                "index": index,
                "reasons": [f"proposal-canonicalization-failed:{type(exc).__name__}"],
            })
            continue

        admitted, identity_reasons, attestation = validate_proposal(
            repo_root, item, proposal_digest
        )
        if not admitted or attestation is None:
            rejected.append({
                "index": index,
                "proposal_digest": proposal_digest,
                "reasons": identity_reasons or ["proposal-attestation-unavailable"],
            })
            continue

        action = CandidateAction(
            action_id=f"model-patch-{index}",
            kind="apply_patch",
            target=target,
            rationale=rationale[:2000],
            expected_gain=metrics["expected_gain"],
            risk=metrics["risk"],
            reversibility=metrics["reversibility"],
            resource_cost=metrics["resource_cost"],
            evidence_gain=metrics["evidence_gain"],
            unified_diff=patch,
            agent_id=attestation.agent_id,
            protocol=attestation.protocol,
            protocol_version=attestation.protocol_version,
            model_id=attestation.model_id,
            model_revision=attestation.model_revision,
            attestation_digest=attestation.attestation_digest,
            invariant_ids=invariant_ids,
            tool_ids=(),
            authority_principal="model",
        )
        allowed, gate_reasons = gate.validate(action)
        if not allowed:
            rejected.append({
                "index": index,
                "proposal_digest": proposal_digest,
                "reasons": gate_reasons,
            })
            continue

        score = planner.score(action)
        row = {
            "schema": SCHEMA,
            "status": "PROPOSED",
            "base_sha": base_sha,
            "proposal_digest": proposal_digest,
            "source_proposal": item,
            "attestation": attestation.as_dict(),
            "action": {
                "action_id": action.action_id,
                "kind": action.kind,
                "target": action.target,
                "rationale": action.rationale,
                **metrics,
                "agent_id": action.agent_id,
                "protocol": action.protocol,
                "protocol_version": action.protocol_version,
                "model_id": action.model_id,
                "model_revision": action.model_revision,
                "attestation_digest": action.attestation_digest,
                "invariant_ids": list(action.invariant_ids),
                "authority_principal": action.authority_principal,
            },
            "unified_diff": patch,
            "validation": {
                "proposal_attestation": "PASS",
                "constitutional_gate": "PASS",
                "risk_policy": "LOW_RISK_ONLY",
                "risk_ceiling": risk_ceiling,
                "planner_score": round(score, 8),
                "patch_bytes": len(patch.encode("utf-8")),
            },
        }
        eligible.append((score, proposal_digest, row))

    if not eligible:
        return {
            "schema": SCHEMA,
            "status": "NO_CANDIDATE",
            "base_sha": base_sha,
            "reason": "no proposal passed identity, low-risk, patch-shape, and constitutional-gate checks",
            "rejected": rejected[:50],
        }

    eligible.sort(key=lambda row: (-row[0], row[1]))
    selected = eligible[0][2]
    selected["validation"]["proposals_considered"] = min(len(proposals), max_proposals)
    selected["validation"]["eligible_candidates"] = len(eligible)
    selected["validation"]["rejected_candidates"] = len(rejected)
    selected["rejected"] = rejected[:50]
    return selected


def build(repo_root: Path, config_path: Path, output_path: Path, *, max_risk: float) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    if git(repo_root, "status", "--porcelain", "--untracked-files=normal"):
        raise RuntimeError("working tree must be clean before creating a patch proposal")

    base_sha = git(repo_root, "rev-parse", "HEAD")
    # Perform destination, identity, protocol and model preflight before
    # constructing the source-context bundle that may be sent to a provider.
    provider = load_provider(repo_root, config_path)
    contract = inspect_contract(repo_root)
    context = ContextWindow(repo_root).build()
    input_bundle = {
        "snapshot": {
            "head": base_sha,
            "working_tree_clean": True,
            "tracked_paths": git(repo_root, "ls-files").splitlines()[:3000],
        },
        "gaps": {
            "canonical_conformance": 0.0 if contract.status == "PASS" else 1.0,
            "missing_conformance_material": list(contract.missing),
        },
        "source_context": context,
        "instructions": {
            "task": "propose one small, reversible application patch that adds measurable value or evidence",
            "constraints": [
                "return a unified git diff for exactly one low-risk patch",
                "do not modify protected CAIOS/AETHEL control surfaces or tests",
                "do not modify specifications, authority, keys, workflows, tool registries, or promotion policy",
                "do not claim tests have run",
                "do not include commands or scripts to execute during proposal generation",
            ],
        },
    }
    proposals = provider.propose(input_bundle)
    return select_candidate(
        repo_root,
        base_sha,
        proposals,
        max_risk=max_risk,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAIOS proposal-only low-risk patch planner")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--config", default="autonomy/agent_endpoints.json")
    parser.add_argument("--output", default="/tmp/caios-patch-proposal.json")
    parser.add_argument("--max-risk", type=float, default=ABSOLUTE_RISK_CEILING)
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    try:
        result = build(root, Path(args.config) if Path(args.config).is_absolute() else root / args.config, output, max_risk=args.max_risk)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "status": "BLOCKED",
            "reason": f"{type(exc).__name__}:{str(exc)[:1000]}",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

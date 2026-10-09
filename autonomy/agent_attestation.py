#!/usr/bin/env python3
"""
CAIOS agent proposal attestation.

An external proposal is admissible only when its declared agent identity and
protocol match the repository-owned registry. This prevents a model response
from presenting itself as an authority merely by choosing a different name.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autonomy.agent_router import AgentRegistry
from autonomy.model_admission import ModelRegistry
from autonomy.protocol_admission import ProtocolRegistry


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ProposalAttestation:
    agent_id: str
    protocol: str
    protocol_version: str
    model_id: str
    model_revision: str
    agent_version: str
    source_ref: str
    proposal_digest: str

    def as_dict(self) -> dict[str, str]:
        return {
            "agent_id": self.agent_id,
            "protocol": self.protocol,
            "protocol_version": self.protocol_version,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "agent_version": self.agent_version,
            "source_ref": self.source_ref,
            "proposal_digest": self.proposal_digest,
        }

    @property
    def attestation_digest(self) -> str:
        return digest(self.as_dict())


def _has_immutable_source_reference(source_ref: str) -> bool:
    if re.fullmatch(r"git:[0-9a-f]{40}(?:[0-9a-f]{24})?", source_ref):
        return True
    try:
        parsed = urllib.parse.urlsplit(source_ref)
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return False
    segments = [part for part in parsed.path.split("/") if part]
    for index, segment in enumerate(segments[:-1]):
        if segment in {"blob", "tree", "commit", "commits"} and re.fullmatch(
            r"[0-9a-f]{40}(?:[0-9a-f]{24})?", segments[index + 1]
        ):
            return True
    return False


def validate_agent_source_binding(
    repo_root: Path,
    profile: Any,
    *,
    agent_version: str,
    source_ref: str,
) -> list[str]:
    """Require proposal identity/version/source to match trusted registry metadata."""
    reasons: list[str] = []
    expected_version = str(getattr(profile, "software_version", "") or "")
    expected_source_ref = str(getattr(profile, "source_ref", "") or "")

    if not expected_version:
        reasons.append("agent-version-not-pinned-by-registry")
    elif agent_version != expected_version:
        reasons.append("agent-version-mismatch")

    if not expected_source_ref:
        reasons.append("agent-source-ref-not-pinned-by-registry")
    elif not _has_immutable_source_reference(expected_source_ref):
        reasons.append("agent-source-ref-not-immutable")
    elif source_ref != expected_source_ref:
        reasons.append("agent-source-ref-mismatch")
    elif not _has_immutable_source_reference(source_ref):
        reasons.append("proposal-source-ref-not-immutable")

    source_path = str(getattr(profile, "source_path", "") or "")
    expected_digest = str(getattr(profile, "source_sha256", "") or "")
    agent_kind = str(getattr(profile, "agent_kind", "external-agent") or "external-agent")
    external_tool_execution = getattr(profile, "external_tool_execution", None)

    if bool(source_path) != bool(expected_digest):
        reasons.append("agent-local-source-pin-incomplete")
    elif source_path and expected_digest:
        root = repo_root.resolve()
        relative = Path(source_path)
        if relative.is_absolute() or ".." in relative.parts:
            reasons.append("agent-local-source-path-invalid")
        else:
            resolved = (root / relative).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                reasons.append("agent-local-source-path-escapes-repository")
            else:
                try:
                    observed_digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
                except OSError:
                    reasons.append("agent-local-source-unavailable")
                else:
                    if observed_digest != expected_digest:
                        reasons.append("agent-local-source-digest-mismatch")

    if agent_kind == "model-proposal-adapter":
        if not source_path or not expected_digest:
            reasons.append("model-proposal-adapter-requires-pinned-local-source")
        if external_tool_execution is not False:
            reasons.append("model-proposal-adapter-must-not-execute-external-tools")
    return reasons


def validate_proposal(
    repo_root: Path,
    proposal: dict[str, Any],
    proposal_digest: str,
) -> tuple[bool, list[str], ProposalAttestation | None]:
    agent_id = str(proposal.get("agent_id", ""))
    protocol = str(proposal.get("protocol", ""))
    protocol_version = str(proposal.get("protocol_version", ""))
    model_id = str(proposal.get("model_id", ""))
    model_revision = str(proposal.get("model_revision", ""))
    agent_version = str(proposal.get("agent_version", ""))
    source_ref = str(proposal.get("source_ref", ""))

    reasons: list[str] = []
    try:
        registry = AgentRegistry(repo_root)
    except Exception as exc:
        return False, [f"agent-registry-unavailable:{type(exc).__name__}"], None

    profile = registry.agents.get(agent_id)
    if profile is None:
        return False, ["agent-id-not-registered"], None
    if profile.authority != "proposal":
        return False, ["agent-is-not-proposal-authority"], None
    if protocol not in profile.protocols:
        return False, ["protocol-not-advertised-by-agent"], None
    expected_protocol_version = profile.protocol_versions.get(protocol)
    source_binding_reasons = validate_agent_source_binding(
        repo_root,
        profile,
        agent_version=agent_version,
        source_ref=source_ref,
    )
    if source_binding_reasons:
        return False, source_binding_reasons, None
    if not expected_protocol_version:
        return False, ["protocol-version-not-pinned-by-agent"], None
    if protocol_version != expected_protocol_version:
        return False, ["protocol-version-mismatch"], None
    if profile.provenance_confidence < float(
        registry.policy.get("minimum_provenance_confidence", 0.90)
    ):
        return False, ["agent-provenance-confidence-below-floor"], None

    try:
        protocol_registry = ProtocolRegistry(repo_root)
        protocol_profile = protocol_registry.get(protocol)
        protocol_ok, protocol_reasons = protocol_registry.admit(
            protocol, protocol_version, allow_draft=False
        )
    except Exception as exc:
        return False, [f"protocol-registry-unavailable:{type(exc).__name__}"], None

    if not protocol_ok:
        return False, [f"protocol-not-admitted:{protocol}:" + ",".join(protocol_reasons)], None
    if protocol_profile is None:
        return False, ["protocol-not-registered"], None
    if protocol_profile.role == "model-proposal-transport" and profile.agent_kind != "model-proposal-adapter":
        return False, ["model-proposal-transport-requires-registered-adapter-identity"], None
    if profile.agent_kind == "model-proposal-adapter" and protocol_profile.role != "model-proposal-transport":
        return False, ["model-proposal-adapter-cannot-claim-agent-execution-protocol"], None

    try:
        model_registry = ModelRegistry(repo_root)
    except Exception as exc:
        return False, [f"model-registry-unavailable:{type(exc).__name__}"], None

    model_admitted, model_reasons = model_registry.admit(
        model_id,
        model_revision=model_revision or None,
    )

    reasons.extend(model_reasons)

    for field_name, value in {
        "protocol_version": protocol_version,
        "model_id": model_id,
        "model_revision": model_revision,
        "agent_version": agent_version,
        "source_ref": source_ref,
    }.items():
        if not value:
            reasons.append(f"{field_name}-missing")

    attestation = None
    if not reasons:
        attestation = ProposalAttestation(
            agent_id=agent_id,
            protocol=protocol,
            protocol_version=protocol_version,
            model_id=model_id,
            model_revision=model_revision,
            agent_version=agent_version,
            source_ref=source_ref,
            proposal_digest=proposal_digest,
        )
    return not reasons, reasons, attestation

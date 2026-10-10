"""Verify local agent source pins against the bytes in this checkout.

This is a regression guard for source-identity drift. It deliberately does not
activate a provider or authorize source-code egress.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_REGISTRY = ROOT / "autonomy" / "agent_registry.json"
ENDPOINT_REGISTRY = ROOT / "autonomy" / "provider_endpoint_registry.json"
COMMIT_REF = re.compile(r"(?:blob|commit|tree)/([0-9a-f]{40}(?:[0-9a-f]{24})?)(?:/|$)")
GIT_REF = re.compile(r"git:[0-9a-f]{40}(?:[0-9a-f]{24})?")


def test_registered_local_agent_source_pins_match_current_bytes() -> None:
    registry = json.loads(AGENT_REGISTRY.read_text(encoding="utf-8"))
    agents = registry.get("agents")
    assert isinstance(agents, list) and agents, "agent registry must contain a list"

    pinned_profiles = [
        agent for agent in agents
        if agent.get("source_path") or agent.get("source_sha256")
    ]
    assert pinned_profiles, "expected at least one local source-pinned agent"

    root = ROOT.resolve()
    model_adapters = []
    for agent in pinned_profiles:
        agent_id = str(agent.get("id") or "<missing-id>")
        source_path = str(agent.get("source_path") or "")
        expected_digest = str(agent.get("source_sha256") or "")
        assert bool(source_path) == bool(expected_digest), (
            f"{agent_id}: source_path and source_sha256 must be configured together"
        )
        assert re.fullmatch(r"[0-9a-f]{64}", expected_digest), (
            f"{agent_id}: source_sha256 must be 64 lowercase hex characters"
        )

        relative = Path(source_path)
        assert not relative.is_absolute() and ".." not in relative.parts, (
            f"{agent_id}: source_path must be repository-relative and traversal-free"
        )
        resolved = (root / relative).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise AssertionError(f"{agent_id}: source_path escapes repository root") from exc
        assert resolved.is_file(), f"{agent_id}: pinned source file does not exist: {source_path}"

        observed = hashlib.sha256(resolved.read_bytes()).hexdigest()
        assert observed == expected_digest, (
            f"{agent_id}: source digest mismatch for {source_path}; "
            f"registry={expected_digest}, observed={observed}"
        )

        if agent.get("agent_kind") == "model-proposal-adapter":
            model_adapters.append(agent)
            assert agent.get("external_tool_execution") is False, (
                f"{agent_id}: proposal-only adapter must not execute external tools"
            )
            assert str(agent.get("software_version") or ""), (
                f"{agent_id}: model-proposal adapter version must be pinned"
            )
            source_ref = str(agent.get("source_ref") or "")
            immutable = bool(
                GIT_REF.fullmatch(source_ref)
                or (
                    source_ref.startswith("https://")
                    and COMMIT_REF.search(source_ref)
                    and not any(part in source_ref for part in ("?", "#"))
                )
            )
            assert immutable, f"{agent_id}: source_ref must pin an immutable full commit"

    assert model_adapters, "expected a registered model-proposal adapter"


def test_remote_provider_allowlist_remains_empty_until_reviewed() -> None:
    registry = json.loads(ENDPOINT_REGISTRY.read_text(encoding="utf-8"))
    assert registry.get("policy", {}).get("unknown_endpoint") == "REJECT"
    assert registry.get("endpoints") == [], (
        "do not enable remote provider egress without a separate reviewed approval record"
    )

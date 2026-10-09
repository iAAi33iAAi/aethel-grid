import json
from pathlib import Path

import pytest

import autonomy.patch_proposal as patch_proposal
from autonomy.agent_attestation import ProposalAttestation


def seed_repo(root: Path) -> None:
    autonomy = root / "autonomy"
    autonomy.mkdir(parents=True)
    (autonomy / "authority_lattice.json").write_text(
        json.dumps({
            "schema": "caios-authority-lattice/v1",
            "principals": [
                {
                    "principal_id": "model",
                    "authority": 10,
                    "capabilities": ["propose"],
                    "boundary": "proposal-only",
                },
                {
                    "principal_id": "caios",
                    "authority": 30,
                    "capabilities": ["supervise", "propose"],
                    "boundary": "repository-root",
                },
            ],
        }),
        encoding="utf-8",
    )
    (autonomy / "agent_registry.json").write_text(
        json.dumps({
            "selection_policy": {"high_risk_threshold": 0.55},
            "agents": [],
        }),
        encoding="utf-8",
    )
    (autonomy / "protected_surfaces.json").write_text(
        json.dumps({"protected_globs": ["src/private/**"]}),
        encoding="utf-8",
    )


def make_patch_proposal(*, risk: float = 0.2, target: str = "src/app.py", kind: str = "apply_patch") -> dict:
    return {
        "kind": kind,
        "target": target,
        "rationale": "add a small, testable improvement",
        "expected_gain": 0.6,
        "risk": risk,
        "reversibility": 1.0,
        "resource_cost": 0.1,
        "evidence_gain": 0.9,
        "unified_diff": (
            f"diff --git a/{target} b/{target}\n"
            f"--- a/{target}\n"
            f"+++ b/{target}\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        ),
        "agent_id": "test-agent",
        "protocol": "openai-compatible",
        "protocol_version": "1.0",
        "model_id": "test-model",
        "model_revision": "test-model@sha256:abc",
        "agent_version": "1.0.0",
        "source_ref": "git:0123456789abcdef",
    }


def install_test_attestation(monkeypatch) -> None:
    def fake_validate(repo_root, proposal, proposal_digest):
        attestation = ProposalAttestation(
            agent_id="test-agent",
            protocol="openai-compatible",
            protocol_version="1.0",
            model_id="test-model",
            model_revision="test-model@sha256:abc",
            agent_version="1.0.0",
            source_ref="git:0123456789abcdef",
            proposal_digest=proposal_digest,
        )
        return True, [], attestation

    monkeypatch.setattr(patch_proposal, "validate_proposal", fake_validate)


def test_select_candidate_returns_low_risk_patch_without_applying_it(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)

    proposal = patch_proposal.select_candidate(
        tmp_path,
        "a" * 40,
        [make_patch_proposal(risk=0.2)],
        max_risk=0.55,
    )

    assert proposal["status"] == "PROPOSED"
    assert proposal["base_sha"] == "a" * 40
    assert proposal["validation"]["constitutional_gate"] == "PASS"
    assert proposal["action"]["risk"] == 0.2
    assert "unified_diff" in proposal
    assert not (tmp_path / "src" / "app.py").exists()


def test_select_candidate_rejects_high_risk_patch(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)

    result = patch_proposal.select_candidate(
        tmp_path,
        "b" * 40,
        [make_patch_proposal(risk=0.55)],
        max_risk=0.55,
    )

    assert result["status"] == "NO_CANDIDATE"
    assert any("risk-not-below-autonomous-ceiling" in reason for row in result["rejected"] for reason in row["reasons"])


def test_select_candidate_rejects_protected_surface_patch(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)

    result = patch_proposal.select_candidate(
        tmp_path,
        "c" * 40,
        [make_patch_proposal(target="conformance/canonical_contract.json")],
        max_risk=0.55,
    )

    assert result["status"] == "NO_CANDIDATE"
    assert any("protected autonomous-control surface" in reason for row in result["rejected"] for reason in row["reasons"])


def test_select_candidate_rejects_non_patch_actions_and_malformed_diffs(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)

    non_patch = make_patch_proposal(kind="run_test")
    malformed = make_patch_proposal()
    malformed["unified_diff"] = "not a unified diff"

    result = patch_proposal.select_candidate(
        tmp_path,
        "d" * 40,
        [non_patch, malformed],
        max_risk=0.55,
    )

    assert result["status"] == "NO_CANDIDATE"
    reasons = [reason for row in result["rejected"] for reason in row["reasons"]]
    assert "only-apply_patch proposals are eligible" in reasons
    assert "unified-diff-malformed" in reasons


def test_select_candidate_rejects_invalid_metrics(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)
    proposal = make_patch_proposal()
    proposal["evidence_gain"] = float("nan")

    result = patch_proposal.select_candidate(
        tmp_path,
        "e" * 40,
        [proposal],
        max_risk=0.55,
    )

    assert result["status"] == "NO_CANDIDATE"
    assert any("invalid-metric" in reason for row in result["rejected"] for reason in row["reasons"])



def write_agent_config(root: Path, *, send_source_context=False, api_key_env=None) -> Path:
    config_path = root / "autonomy" / "agent_endpoints.json"
    row = {
        "agent_id": "test-agent",
        "endpoint": "https://example.invalid/v1/chat/completions",
        "model": "test-model",
        "protocol": "openai-compatible",
        "agent_version": "1.0.0",
        "source_ref": "git:0123456789abcdef",
        "send_source_context": send_source_context,
    }
    if api_key_env is not None:
        row["api_key_env"] = api_key_env
    config_path.write_text(json.dumps({"agents": [row]}), encoding="utf-8")
    return config_path


def test_agent_config_rejects_string_egress_flag(tmp_path: Path):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context="false")

    with pytest.raises(ValueError, match="send_source_context must be a JSON boolean"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_agent_config_rejects_unscoped_api_key_environment_name(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    monkeypatch.setenv("PATH", "/usr/bin")
    config_path = write_agent_config(
        tmp_path,
        send_source_context=True,
        api_key_env="PATH",
    )

    with pytest.raises(ValueError, match="approved CAIOS_\\*_API_KEY"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_agent_config_requires_explicit_source_context_opt_in(tmp_path: Path):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=False)

    with pytest.raises(ValueError, match="explicitly enable send_source_context"):
        patch_proposal.load_provider(tmp_path, config_path)



def setup_preflight_registries(monkeypatch, *, agents, model_ok=True, protocol_ok=True):
    class FakeAgentRegistry:
        def __init__(self, repo_root):
            self.policy = {"minimum_provenance_confidence": 0.90}
            self.agents = agents

    class FakeModelRegistry:
        def __init__(self, repo_root):
            pass

        def admit(self, model_id, *, model_revision=None):
            return model_ok, [] if model_ok else ["model-id-not-registered"]

    class FakeProtocolRegistry:
        def __init__(self, repo_root):
            pass

        def admit(self, protocol_id, version, *, allow_draft=False):
            return protocol_ok, [] if protocol_ok else ["protocol-not-registered"]

    monkeypatch.setattr(patch_proposal, "AgentRegistry", FakeAgentRegistry)
    monkeypatch.setattr(patch_proposal, "ModelRegistry", FakeModelRegistry)
    monkeypatch.setattr(patch_proposal, "ProtocolRegistry", FakeProtocolRegistry)


def endpoint_profile(
    *,
    authority="proposal",
    protocols=("mcp",),
    capabilities=("coding", "patching"),
    provenance_confidence=0.99,
    protocol_versions=None,
):
    from types import SimpleNamespace

    return SimpleNamespace(
        authority=authority,
        protocols=frozenset(protocols),
        capabilities=frozenset(capabilities),
        provenance_confidence=provenance_confidence,
        protocol_versions=protocol_versions or {"mcp": "2026-07-28"},
    )


def test_provider_preflight_rejects_unregistered_agent_before_returning_provider(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    setup_preflight_registries(monkeypatch, agents={})

    with pytest.raises(ValueError, match="agent-id-not-registered:test-agent"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_protocol_not_advertised_by_agent(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(protocols=("acp",), protocol_versions={"acp": "1"})
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile})

    with pytest.raises(ValueError, match="agent-protocol-not-registered:test-agent:openai-compatible"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_protocol_missing_from_protocol_registry(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(
        protocols=("openai-compatible",),
        protocol_versions={"openai-compatible": "1.0.0"},
    )
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile}, protocol_ok=False)

    with pytest.raises(ValueError, match="protocol-not-admitted:openai-compatible:1.0.0"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_unregistered_model_before_returning_provider(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile()
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile}, model_ok=False)

    with pytest.raises(ValueError, match="model-not-admitted:test-model:model-id-not-registered"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_agent_without_patch_capability(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(capabilities=("reasoning", "planning"))
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile})

    with pytest.raises(ValueError, match="agent-lacks-coding-or-patching-capability:test-agent"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_unpinned_agent_protocol_version(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(
        protocols=("openai-compatible",),
        protocol_versions={},
    )
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile})

    with pytest.raises(ValueError, match="agent-protocol-version-not-pinned:test-agent:openai-compatible"):
        patch_proposal.load_provider(tmp_path, config_path)

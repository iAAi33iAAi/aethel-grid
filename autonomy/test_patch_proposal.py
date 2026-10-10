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
    (autonomy / "provider_endpoint_registry.json").write_text(
        json.dumps({
            "schema": "caios-provider-endpoints/v1",
            "policy": {
                "unknown_endpoint": "REJECT",
                "exact_url_match": True,
                "exact_agent_model_protocol_match": True,
                "require_approval_ref": True,
            },
            "endpoints": [{
                "id": "test-endpoint",
                "endpoint_url": "https://example.invalid/v1/chat/completions",
                "agent_id": "test-agent",
                "agent_version": "1.0.0",
                "source_ref": "git:0123456789012345678901234567890123456789",
                "protocol": "caios-openai-compatible-proposal-transport",
                "protocol_version": "1.0.0",
                "model_id": "test-model",
                "model_revision": "test-model@sha256:abc",
                "approval_ref": "test-fixture-only",
                "api_key_env": None,
            }],
        }),
        encoding="utf-8",
    )
    (autonomy / "caios_runtime.py").write_text(
        "trusted test adapter\n",
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
        "protocol": "caios-openai-compatible-proposal-transport",
        "protocol_version": "1.0.0",
        "model_id": "test-model",
        "model_revision": "test-model@sha256:abc",
        "agent_version": "1.0.0",
        "source_ref": "git:0123456789012345678901234567890123456789",
    }


def install_test_attestation(monkeypatch) -> None:
    def fake_validate(repo_root, proposal, proposal_digest):
        attestation = ProposalAttestation(
            agent_id="test-agent",
            protocol="caios-openai-compatible-proposal-transport",
            protocol_version="1.0.0",
            model_id="test-model",
            model_revision="test-model@sha256:abc",
            agent_version="1.0.0",
            source_ref="git:0123456789012345678901234567890123456789",
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



def write_agent_config(
    root: Path,
    *,
    send_source_context=False,
    api_key_env=None,
    protocol="caios-openai-compatible-proposal-transport",
    protocol_version="1.0.0",
    endpoint="https://example.invalid/v1/chat/completions",
    endpoint_id="test-endpoint",
    agent_id="test-agent",
    model="test-model",
    model_revision="test-model@sha256:abc",
) -> Path:
    config_path = root / "autonomy" / "agent_endpoints.json"
    row = {
        "endpoint_id": endpoint_id,
        "agent_id": agent_id,
        "endpoint": endpoint,
        "model": model,
        "model_revision": model_revision,
        "protocol": protocol,
        "protocol_version": protocol_version,
        "agent_version": "1.0.0",
        "source_ref": "git:0123456789012345678901234567890123456789",
        "send_source_context": send_source_context,
    }
    if api_key_env is not None:
        row["api_key_env"] = api_key_env
    config_path.write_text(
        json.dumps({"schema": "caios-agent-endpoints/v1", "agents": [row]}),
        encoding="utf-8",
    )
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

        def get(self, protocol_id):
            from types import SimpleNamespace
            role = (
                "model-proposal-transport"
                if protocol_id == "caios-openai-compatible-proposal-transport"
                else "agent-client"
            )
            return SimpleNamespace(role=role)

        def admit(self, protocol_id, version, *, allow_draft=False):
            return protocol_ok, [] if protocol_ok else ["protocol-not-registered"]

    monkeypatch.setattr(patch_proposal, "AgentRegistry", FakeAgentRegistry)
    monkeypatch.setattr(patch_proposal, "ModelRegistry", FakeModelRegistry)
    monkeypatch.setattr(patch_proposal, "ProtocolRegistry", FakeProtocolRegistry)


def endpoint_profile(
    *,
    authority="proposal",
    protocols=("caios-openai-compatible-proposal-transport",),
    capabilities=("coding", "patching"),
    provenance_confidence=0.99,
    protocol_versions=None,
    software_version="1.0.0",
    source_ref="git:0123456789012345678901234567890123456789",
    agent_kind="model-proposal-adapter",
    source_path="autonomy/caios_runtime.py",
    source_sha256="57a550fa4fe91d4a7ccc49852764e569abaa826c863082089ab8368d14a8e444",
    external_tool_execution=False,
):
    from types import SimpleNamespace

    return SimpleNamespace(
        authority=authority,
        protocols=frozenset(protocols),
        capabilities=frozenset(capabilities),
        provenance_confidence=provenance_confidence,
        protocol_versions=(
            protocol_versions if protocol_versions is not None
            else {"caios-openai-compatible-proposal-transport": "1.0.0"}
        ),
        software_version=software_version,
        source_ref=source_ref,
        agent_kind=agent_kind,
        source_path=source_path,
        source_sha256=source_sha256,
        external_tool_execution=external_tool_execution,
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

    with pytest.raises(ValueError, match="agent-protocol-not-registered:test-agent:caios-openai-compatible-proposal-transport"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_protocol_missing_from_protocol_registry(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(
        protocols=("caios-openai-compatible-proposal-transport",),
        protocol_versions={"caios-openai-compatible-proposal-transport": "1.0.0"},
    )
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile}, protocol_ok=False)

    with pytest.raises(ValueError, match="protocol-not-admitted:caios-openai-compatible-proposal-transport:1.0.0"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_unregistered_model_before_returning_provider(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(
        protocols=("caios-openai-compatible-proposal-transport",),
        protocol_versions={"caios-openai-compatible-proposal-transport": "1.0.0"},
    )
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile}, model_ok=False)

    with pytest.raises(ValueError, match="model-not-admitted:test-model:model-id-not-registered"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_agent_without_patch_capability(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(
        protocols=("caios-openai-compatible-proposal-transport",),
        capabilities=("reasoning", "planning"),
        protocol_versions={"caios-openai-compatible-proposal-transport": "1.0.0"},
    )
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile})

    with pytest.raises(ValueError, match="agent-lacks-coding-or-patching-capability:test-agent"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_unpinned_agent_protocol_version(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(
        protocols=("caios-openai-compatible-proposal-transport",),
        protocol_versions={},
    )
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile})

    with pytest.raises(ValueError, match="agent-protocol-version-not-pinned:test-agent:caios-openai-compatible-proposal-transport"):
        patch_proposal.load_provider(tmp_path, config_path)



def test_provider_preflight_rejects_unregistered_endpoint_id(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(
        tmp_path,
        send_source_context=True,
        endpoint_id="unreviewed-endpoint",
    )
    setup_preflight_registries(monkeypatch, agents={})

    with pytest.raises(ValueError, match="provider-endpoint-not-registered:unreviewed-endpoint"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_url_that_differs_from_reviewed_binding(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(
        tmp_path,
        send_source_context=True,
        endpoint="https://attacker.invalid/v1/chat/completions",
    )
    setup_preflight_registries(monkeypatch, agents={})

    with pytest.raises(ValueError, match="provider-endpoint-binding-mismatch:test-endpoint:endpoint_url"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_embedded_endpoint_credentials(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(
        tmp_path,
        send_source_context=True,
        endpoint="https://user:secret@example.invalid/v1/chat/completions",
    )
    setup_preflight_registries(monkeypatch, agents={})

    with pytest.raises(ValueError, match="must not include credentials"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_missing_endpoint_registry(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    (tmp_path / "autonomy" / "provider_endpoint_registry.json").unlink()
    config_path = write_agent_config(tmp_path, send_source_context=True)
    setup_preflight_registries(monkeypatch, agents={})

    with pytest.raises(ValueError, match="provider-endpoint-registry-unavailable"):
        patch_proposal.load_provider(tmp_path, config_path)



def test_provider_preflight_requires_exact_agent_model_and_protocol_binding(tmp_path: Path, monkeypatch):
    mismatches = [
        {"agent_id": "another-agent"},
        {"model": "another-model"},
        {"model_revision": "test-model@sha256:different"},
        {"protocol": "acp"},
        {"protocol_version": "another-version"},
    ]
    for index, override in enumerate(mismatches):
        case_root = tmp_path / str(index)
        case_root.mkdir(parents=True)
        seed_repo(case_root)
        config_path = write_agent_config(
            case_root,
            send_source_context=True,
            **override,
        )
        setup_preflight_registries(monkeypatch, agents={})
        with pytest.raises(ValueError, match="provider-endpoint-binding-mismatch"):
            patch_proposal.load_provider(case_root, config_path)


def test_build_rejects_unregistered_endpoint_before_building_source_context(tmp_path: Path, monkeypatch):
    import subprocess

    seed_repo(tmp_path)
    config_path = write_agent_config(
        tmp_path,
        send_source_context=True,
        endpoint_id="unregistered-before-context",
    )
    subprocess.run(("git", "init"), cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(("git", "config", "user.email", "caios@test"), cwd=tmp_path, check=True)
    subprocess.run(("git", "config", "user.name", "CAIOS Test"), cwd=tmp_path, check=True)
    subprocess.run(("git", "add", "."), cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(("git", "commit", "-m", "fixture"), cwd=tmp_path, capture_output=True, check=True)

    class SourceContextMustNotBeBuilt:
        def __init__(self, repo_root):
            raise AssertionError("source context must not be built before endpoint preflight")

    monkeypatch.setattr(patch_proposal, "ContextWindow", SourceContextMustNotBeBuilt)

    with pytest.raises(ValueError, match="provider-endpoint-not-registered:unregistered-before-context"):
        patch_proposal.build(
            tmp_path,
            config_path,
            tmp_path / "out.json",
            max_risk=0.45,
        )



def test_provider_preflight_rejects_agent_provenance_mismatch(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(
        tmp_path,
        send_source_context=True,
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["agents"][0]["source_ref"] = "git:unreviewed-source"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    setup_preflight_registries(monkeypatch, agents={})

    with pytest.raises(ValueError, match="provider-endpoint-binding-mismatch:test-endpoint:source_ref"):
        patch_proposal.load_provider(tmp_path, config_path)



def test_provider_preflight_binds_the_api_key_secret_name_to_endpoint(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    monkeypatch.setenv("CAIOS_OTHER_API_KEY", "test-only-secret")
    config_path = write_agent_config(
        tmp_path,
        send_source_context=True,
        api_key_env="CAIOS_OTHER_API_KEY",
    )
    setup_preflight_registries(monkeypatch, agents={})

    with pytest.raises(ValueError, match="provider-endpoint-binding-mismatch:test-endpoint:api_key_env"):
        patch_proposal.load_provider(tmp_path, config_path)



def test_provider_preflight_rejects_agent_source_ref_claim_not_in_registry(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(source_ref="git:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile})

    with pytest.raises(ValueError, match="agent-identity-binding-failed:test-agent:agent-source-ref-mismatch"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_agent_software_version_not_pinned(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(software_version="")
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile})

    with pytest.raises(ValueError, match="agent-version-not-pinned-by-registry"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_http_transport_claimed_as_external_agent(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(agent_kind="external-agent")
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile})

    with pytest.raises(ValueError, match="model-proposal-transport-requires-adapter-identity:test-agent"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_provider_preflight_rejects_adapter_that_claims_external_tool_execution(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    config_path = write_agent_config(tmp_path, send_source_context=True)
    profile = endpoint_profile(external_tool_execution=True)
    setup_preflight_registries(monkeypatch, agents={"test-agent": profile})

    with pytest.raises(ValueError, match="agent-identity-binding-failed:test-agent:model-proposal-adapter-must-not-execute-external-tools"):
        patch_proposal.load_provider(tmp_path, config_path)


def test_select_candidate_rejects_nonfinite_max_risk(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)
    with pytest.raises(ValueError, match="max_risk must be a finite number within"):
        patch_proposal.select_candidate(
            tmp_path,
            "f" * 40,
            [make_patch_proposal(risk=0.54)],
            max_risk=float("nan"),
        )


def test_select_candidate_rejects_nonfinite_registered_risk_threshold(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)
    path = tmp_path / "autonomy" / "agent_registry.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["selection_policy"]["high_risk_threshold"] = float("nan")
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="registered high_risk_threshold must be a finite number"):
        patch_proposal.select_candidate(
            tmp_path,
            "f" * 40,
            [make_patch_proposal(risk=0.54)],
            max_risk=0.55,
        )


def test_select_candidate_rejects_huge_integer_and_boolean_metrics(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)
    proposals = [make_patch_proposal(), make_patch_proposal()]
    proposals[0]["expected_gain"] = 10 ** 10000
    proposals[1]["risk"] = True
    result = patch_proposal.select_candidate(
        tmp_path,
        "f" * 40,
        proposals,
        max_risk=0.55,
    )
    assert result["status"] == "NO_CANDIDATE"
    reasons = [reason for row in result["rejected"] for reason in row["reasons"]]
    assert sum("invalid-metric" in reason for reason in reasons) == 2


@pytest.mark.parametrize(
    ("field", "value", "expected_reason"),
    [
        ("target", [], "target-must-be-non-empty-string"),
        ("rationale", {"unexpected": "object"}, "rationale-must-be-string"),
        ("invariant_ids", "ID-1", "invariant-ids-must-be-string-array"),
        ("tool_ids", 7, "tool-ids-must-be-string-array"),
    ],
)
def test_select_candidate_rejects_malformed_action_metadata(tmp_path: Path, monkeypatch, field, value, expected_reason):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)
    proposal = make_patch_proposal()
    proposal[field] = value
    result = patch_proposal.select_candidate(
        tmp_path,
        "f" * 40,
        [proposal],
        max_risk=0.55,
    )
    assert result["status"] == "NO_CANDIDATE"
    assert expected_reason in [reason for row in result["rejected"] for reason in row["reasons"]]


def test_select_candidate_rejects_huge_integer_in_unrecognized_field_during_digest(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)
    proposal = make_patch_proposal()
    proposal["unrecognized_numeric_extension"] = 10 ** 10000

    result = patch_proposal.select_candidate(
        tmp_path,
        "f" * 40,
        [proposal],
        max_risk=0.55,
    )
    assert result["status"] == "NO_CANDIDATE"
    assert "proposal-canonicalization-failed:ValueError" in [
        reason for row in result["rejected"] for reason in row["reasons"]
    ]


def test_select_candidate_rejects_multi_file_patch(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)
    proposal = make_patch_proposal()
    second_file = (
        "diff --git a/src/second.py b/src/second.py\n"
        "--- a/src/second.py\n"
        "+++ b/src/second.py\n"
        "@@ -1 +1 @@\n-old\n+new\n"
    )
    proposal["unified_diff"] += second_file

    result = patch_proposal.select_candidate(
        tmp_path,
        "f" * 40,
        [proposal],
        max_risk=0.55,
    )
    assert result["status"] == "NO_CANDIDATE"
    assert "unified-diff-must-target-exactly-one-file" in [
        reason for row in result["rejected"] for reason in row["reasons"]
    ]


def test_select_candidate_rejects_conflicting_diff_header_paths(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)
    proposal = make_patch_proposal()
    proposal["unified_diff"] = proposal["unified_diff"].replace(
        "diff --git a/src/app.py b/src/app.py",
        "diff --git a/src/app.py b/src/other.py",
    )

    result = patch_proposal.select_candidate(
        tmp_path,
        "f" * 40,
        [proposal],
        max_risk=0.55,
    )
    assert result["status"] == "NO_CANDIDATE"
    assert "unified-diff-header-path-mismatch" in [
        reason for row in result["rejected"] for reason in row["reasons"]
    ]

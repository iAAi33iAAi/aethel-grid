from pathlib import Path
import hashlib
import json
from types import SimpleNamespace

from autonomy.agent_attestation import validate_proposal


def test_unregistered_agent_is_rejected(tmp_path: Path):
    registry = tmp_path / "autonomy"
    registry.mkdir()
    (registry / "agent_registry.json").write_text(
        """{
          "selection_policy": {"minimum_provenance_confidence":0.9},
          "agents": []
        }""",
        encoding="utf-8",
    )
    ok, reasons, attestation = validate_proposal(
        tmp_path,
        {
            "agent_id": "unknown",
            "protocol": "acp",
            "model_id": "model",
            "agent_version": "1",
            "source_ref": "unknown",
        },
        "proposal",
    )
    assert ok is False
    assert attestation is None
    assert "agent-id-not-registered" in reasons


def test_registered_proposal_gets_attestation(tmp_path: Path):
    registry = tmp_path / "autonomy"
    registry.mkdir()
    (registry / "agent_registry.json").write_text(
        """{
          "selection_policy": {"minimum_provenance_confidence":0.9},
          "agents": [
            {
              "id":"coder",
              "family":"coder",
              "protocols":["acp"],
              "protocol_versions":{"acp":"1"},
              "capabilities":["coding"],
              "authority":"proposal",
              "license":"MIT",
              "sandbox":true,
              "provenance_confidence":1.0,
              "software_version":"2026.10",
              "source_ref":"git:abc"
            }
          ]
        }""",
        encoding="utf-8",
    )
    (tmp_path / "autonomy/protocol_registry.json").write_text(
        json.dumps({
            "policy": {
                "unknown_protocol": "REJECT",
                "draft_protocol_requires_opt_in": True,
                "major_version_mismatch": "REJECT",
                "capabilities_are_advisory": True,
            },
            "protocols": [{
                "id": "acp",
                "latest_known_revision": "1",
                "status": "stable",
                "transport_role": "agent-client",
                "license": "Apache-2.0",
                "source_url": "https://github.com/agentclientprotocol/agent-client-protocol",
                "draft": False,
            }],
        }),
        encoding="utf-8",
    )
    (tmp_path / "autonomy/model_registry.json").write_text(
        """{
          "policy": {
            "service_terms_required": true,
            "weight_license_required": true,
            "source_commit_required_for_local_weights": true
          },
          "models": [
            {
              "model_id": "coder-model",
              "class": "hosted-service",
              "software_license": "N/A",
              "weight_license": "N/A",
              "service_terms_status": "REVIEWED",
              "redistribution": "N/A",
              "production": "ALLOWED_AFTER_REVIEW",
              "terms_ref": "operator-reviewed-terms"
            }
          ]
        }""",
        encoding="utf-8",
    )
    ok, reasons, attestation = validate_proposal(
        tmp_path,
        {
            "agent_id": "coder",
            "protocol": "acp",
            "protocol_version": "1",
            "model_id": "coder-model",
            "model_revision": "hosted-reviewed",
            "agent_version": "2026.10",
            "source_ref": "git:abc",
        },
        "proposal",
    )
    assert ok is True
    assert reasons == []
    assert attestation is not None
    assert attestation.agent_id == "coder"
    assert attestation.attestation_digest



def test_agent_source_binding_rejects_version_and_source_mismatch(tmp_path: Path):
    from autonomy.agent_attestation import validate_agent_source_binding

    profile = SimpleNamespace(
        software_version="1.2.3",
        source_ref="git:trusted-source",
        agent_kind="external-agent",
        source_path="",
        source_sha256="",
        external_tool_execution=None,
    )

    assert "agent-version-mismatch" in validate_agent_source_binding(
        tmp_path, profile, agent_version="9.9.9", source_ref="git:trusted-source"
    )
    assert "agent-source-ref-mismatch" in validate_agent_source_binding(
        tmp_path, profile, agent_version="1.2.3", source_ref="git:untrusted-source"
    )


def test_agent_source_binding_checks_pinned_local_adapter_digest(tmp_path: Path):
    from autonomy.agent_attestation import validate_agent_source_binding

    autonomy = tmp_path / "autonomy"
    autonomy.mkdir()
    source = autonomy / "adapter.py"
    source.write_text("approved adapter\n", encoding="utf-8")
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    profile = SimpleNamespace(
        software_version="1.0.0",
        source_ref="git:adapter-source",
        agent_kind="model-proposal-adapter",
        source_path="autonomy/adapter.py",
        source_sha256=expected,
        external_tool_execution=False,
    )

    assert validate_agent_source_binding(
        tmp_path, profile, agent_version="1.0.0", source_ref="git:adapter-source"
    ) == []

    source.write_text("tampered adapter\n", encoding="utf-8")
    assert "agent-local-source-digest-mismatch" in validate_agent_source_binding(
        tmp_path, profile, agent_version="1.0.0", source_ref="git:adapter-source"
    )



def test_registered_proposal_adapter_source_pin_matches_checkout():
    from autonomy.agent_attestation import validate_agent_source_binding
    from autonomy.agent_router import AgentRegistry
    from autonomy.protocol_admission import ProtocolRegistry

    repo_root = Path(__file__).resolve().parents[1]
    profile = AgentRegistry(repo_root).agents["caios-openai-compatible-proposal-adapter"]
    protocol = ProtocolRegistry(repo_root).get("caios-openai-compatible-proposal-transport")

    assert profile.agent_kind == "model-proposal-adapter"
    assert profile.external_tool_execution is False
    assert protocol is not None
    assert protocol.role == "model-proposal-transport"
    assert protocol.version == "1.0.0"
    assert validate_agent_source_binding(
        repo_root,
        profile,
        agent_version=profile.software_version,
        source_ref=profile.source_ref,
    ) == []

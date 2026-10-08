from pathlib import Path

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
              "provenance_confidence":1.0
            }
          ]
        }""",
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

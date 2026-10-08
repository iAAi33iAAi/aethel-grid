import json
from pathlib import Path

from autonomy.proof_work_contract import ProofCarryingWorkContract
from autonomy.proof_work_verifier import verify_contract


def fixture_root(tmp_path: Path):
    (tmp_path / "autonomy").mkdir()
    (tmp_path / "integrations").mkdir()
    (tmp_path / "conformance").mkdir()

    (tmp_path / "autonomy/protocol_registry.json").write_text(json.dumps({
        "policy":{"draft_protocol_requires_opt_in":True},
        "protocols":[{
            "id":"acp",
            "latest_known_revision":"1",
            "status":"stable",
            "transport_role":"agent-client",
            "license":"Apache-2.0",
            "source_url":"https://github.com/agentclientprotocol/agent-client-protocol",
            "draft":False
        }]
    }), encoding="utf-8")
    (tmp_path / "autonomy/agent_registry.json").write_text(json.dumps({
        "selection_policy":{"minimum_provenance_confidence":0.9},
        "agents":[{
            "id":"coder",
            "family":"coder",
            "protocols":["acp"],
            "protocol_versions":{"acp":"1"},
            "capabilities":["coding"],
            "authority":"proposal",
            "license":"Apache-2.0",
            "sandbox":True,
            "provenance_confidence":1.0
        }]
    }), encoding="utf-8")
    (tmp_path / "autonomy/model_registry.json").write_text(json.dumps({
        "policy":{},
        "models":[{
            "model_id":"m",
            "class":"hosted-service",
            "software_license":"N/A",
            "weight_license":"N/A",
            "service_terms_status":"REVIEWED",
            "redistribution":"N/A",
            "production":"ALLOWED"
        }]
    }), encoding="utf-8")
    (tmp_path / "integrations/caios_tool_registry.json").write_text(json.dumps({
        "policy":{},
        "tools":[{"id":"pytest","capability":"verification","authority":"deterministic","license":"MIT","command":["python","-m","pytest","-q"]}]
    }), encoding="utf-8")
    return tmp_path


def test_valid_contract_cross_checks_registries(tmp_path: Path):
    root = fixture_root(tmp_path)
    contract = ProofCarryingWorkContract(
        work_id="w1",
        intent_fingerprint="a"*64,
        action_kind="run_test",
        state_before="b"*64,
        state_after=None,
        protocol="acp",
        protocol_version="1",
        agent_id="coder",
        model_id="m",
        model_revision="rev",
        agent_attestation="c"*64,
        tool_ids=("pytest",),
        invariant_ids=("INV-013",),
        risk=0.5,
    )
    ok, reasons = verify_contract(root, contract)
    assert ok is True
    assert reasons == []


def test_high_risk_pass_without_simulation_is_rejected(tmp_path: Path):
    root = fixture_root(tmp_path)
    contract = ProofCarryingWorkContract(
        work_id="w2",
        intent_fingerprint="a"*64,
        action_kind="apply_patch",
        state_before="b"*64,
        state_after="d"*64,
        protocol="acp",
        protocol_version="1",
        agent_id="coder",
        model_id="m",
        model_revision="rev",
        agent_attestation="c"*64,
        tool_ids=("pytest",),
        invariant_ids=("INV-013",),
        risk=0.8,
        decision="PASS",
        execution_digest="e"*64,
    )
    ok, reasons = verify_contract(root, contract)
    assert ok is False
    assert "high-risk-passed-work-requires-simulation-digest" in reasons

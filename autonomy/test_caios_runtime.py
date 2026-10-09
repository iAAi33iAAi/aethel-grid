"""
CAIOS runtime tests.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
import json
from pathlib import Path

from autonomy.caios_runtime import CandidateAction, ConstitutionalGate, RedTeamObserver, ViabilityPlanner
from autonomy.red_team import probes as red_team_probes


def _seed_authority(tmp_path: Path) -> None:
    path = tmp_path / "autonomy"
    path.mkdir(exist_ok=True)
    (path / "authority_lattice.json").write_text(
        json.dumps({
            "schema": "caios-authority-lattice/v1",
            "principals": [
                {"principal_id": "model", "authority": 10, "capabilities": ["propose"], "boundary": "proposal-only"},
                {"principal_id": "caios", "authority": 30, "capabilities": ["policy", "supervise"], "boundary": "test"},
            ],
        }),
        encoding="utf-8",
    )

def test_gate_rejects_escape_target(tmp_path: Path):
    _seed_authority(tmp_path)
    gate = ConstitutionalGate(tmp_path)
    action = CandidateAction(
        action_id="bad",
        kind="run_test",
        target="../outside",
        rationale="escape",
        expected_gain=0.5,
        risk=0.1,
        reversibility=1.0,
        resource_cost=0.1,
        evidence_gain=0.5,
    )
    allowed, reasons = gate.validate(action)
    assert allowed is False
    assert any("escapes" in reason for reason in reasons)


def test_gate_rejects_high_risk_model_action(tmp_path: Path):
    _seed_authority(tmp_path)
    gate = ConstitutionalGate(tmp_path)
    action = CandidateAction(
        action_id="danger",
        kind="run_test",
        target=".",
        rationale="danger",
        expected_gain=0.9,
        risk=0.99,
        reversibility=0.2,
        resource_cost=0.1,
        evidence_gain=0.8,
    )
    allowed, reasons = gate.validate(action)
    assert allowed is False
    assert len(reasons) >= 2


def test_viability_score_prefers_evidence_and_reversibility():
    planner = ViabilityPlanner()
    safe = CandidateAction(
        action_id="safe",
        kind="run_test",
        target=".",
        rationale="safe",
        expected_gain=0.6,
        risk=0.1,
        reversibility=1.0,
        resource_cost=0.2,
        evidence_gain=0.95,
    )
    risky = CandidateAction(
        action_id="risky",
        kind="apply_patch",
        target=".",
        rationale="risky",
        expected_gain=0.9,
        risk=0.8,
        reversibility=0.4,
        resource_cost=0.4,
        evidence_gain=0.6,
    )
    assert planner.score(safe) > planner.score(risky)


def test_certificate_proof_seal_is_self_consistent(tmp_path: Path):
    from autonomy.caios_runtime import DecisionCertificate, Evidence, write_certificates
    from autonomy.verify_certificates import verify

    certificate = DecisionCertificate(
        cycle=1,
        selected_action=None,
        decision="HALT",
        score=0.0,
        gaps_before={"conformance": 1.0},
        evidence=(Evidence("session-anchor", "PASS", "test", "abc", {"session_id":"s1"}),),
        reasons=("blocked",),
        action_fingerprint=None,
        previous_certificate_digest=None,
        elapsed_ms=1,
        session_id="s1",
        session_anchor_hash="abc",
    )
    output = tmp_path / "certificates.jsonl"
    write_certificates([certificate], output)
    assert verify(output)[0] is True


def test_proof_graph_contains_certificate_chain():
    from autonomy.proof_graph import build_proof_graph

    certificate = {
        "cycle": 1,
        "proof_digest": "proof",
        "observation_digest": "obs",
        "council_digest": "council",
        "action_fingerprint": "action",
        "selected_action": "run-tests",
        "decision": "CONTINUE",
        "evidence": [
            {"kind": "test", "status": "PASS", "source": "pytest", "digest": "ev1", "details": {}}
        ],
    }
    graph = build_proof_graph(certificate)
    assert graph["schema"] == "caios-proof-graph/v1"
    assert any(edge["relation"] == "supports" for edge in graph["edges"])


def test_gate_accepts_caios_policy_action_when_authority_is_present(tmp_path: Path):
    _seed_authority(tmp_path)
    gate = ConstitutionalGate(tmp_path)
    action = CandidateAction(
        action_id="observe",
        kind="observe",
        target=".",
        rationale="trusted supervisor observation",
        expected_gain=0.2,
        risk=0.05,
        reversibility=1.0,
        resource_cost=0.05,
        evidence_gain=0.5,
    )
    allowed, reasons = gate.validate(action)
    assert allowed is True, reasons


def test_red_team_observer_executes_campaign_inside_runtime():
    repo_root = Path(__file__).resolve().parents[1]
    evidence = RedTeamObserver().observe(repo_root)
    assert evidence.kind == "red-team"
    assert evidence.status == "PASS", evidence.details
    assert evidence.details["probe_count"] == len(red_team_probes())
    assert evidence.details["probe_count"] >= 48


def test_missing_authority_lattice_fails_closed(tmp_path: Path):
    gate = ConstitutionalGate(tmp_path)
    action = CandidateAction(
        action_id="blocked",
        kind="observe",
        target=".",
        rationale="authority must exist",
        expected_gain=0.1,
        risk=0.01,
        reversibility=1.0,
        resource_cost=0.01,
        evidence_gain=0.1,
    )
    allowed, reasons = gate.validate(action)
    assert allowed is False
    assert any("authority-lattice-unavailable" in reason for reason in reasons)


def test_malformed_authority_principal_fails_closed(tmp_path: Path):
    path = tmp_path / "autonomy"
    path.mkdir()
    (path / "authority_lattice.json").write_text(
        "{\"schema\":\"caios-authority-lattice/v1\",\"principals\":[{\"principal_id\":\"caios\",\"authority\":\"not-a-number\"}]}\n",
        encoding="utf-8",
    )
    gate = ConstitutionalGate(tmp_path)
    action = CandidateAction(
        action_id="blocked",
        kind="observe",
        target=".",
        rationale="malformed authority must not authorize",
        expected_gain=0.1,
        risk=0.01,
        reversibility=1.0,
        resource_cost=0.01,
        evidence_gain=0.1,
    )
    allowed, reasons = gate.validate(action)
    assert allowed is False
    assert any("authority-lattice-unavailable" in reason for reason in reasons)

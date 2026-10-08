"""
CAIOS runtime tests.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from pathlib import Path

from autonomy.caios_runtime import CandidateAction, ConstitutionalGate, ViabilityPlanner


def test_gate_rejects_escape_target(tmp_path: Path):
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
        evidence=(Evidence("gate", "BLOCKED", "test", "abc", {}),),
        reasons=("blocked",),
        action_fingerprint=None,
        previous_certificate_digest=None,
        elapsed_ms=1,
    )
    output = tmp_path / "certificates.jsonl"
    write_certificates([certificate], output)
    assert verify(output)[0] is True

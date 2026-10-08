from pathlib import Path

from autonomy.agent_reputation import AgentReputationStore


def test_reputation_starts_neutral(tmp_path: Path):
    store = AgentReputationStore(tmp_path / "rep.jsonl")
    assert store.score("agent") == 0.5


def test_failed_rollback_is_heavily_penalized(tmp_path: Path):
    store = AgentReputationStore(tmp_path / "rep.jsonl")
    store.record(
        "agent",
        action_kind="apply_patch",
        outcome="FAIL",
        test_pass=False,
        evidence_gain=0.0,
        risk=0.9,
        rollback=True,
    )
    assert store.score("agent") < 0.20


def test_successful_verified_actions_raise_reputation(tmp_path: Path):
    store = AgentReputationStore(tmp_path / "rep.jsonl")
    for _ in range(5):
        store.record(
            "agent",
            action_kind="run_test",
            outcome="PASS",
            test_pass=True,
            evidence_gain=1.0,
            risk=0.1,
            rollback=False,
        )
    assert store.score("agent") > 0.90

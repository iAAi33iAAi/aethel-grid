import json
from pathlib import Path

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
        [patch_proposal.make_patch_proposal(risk=0.2)],
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
        [patch_proposal.make_patch_proposal(risk=0.55)],
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
        [patch_proposal.make_patch_proposal(target="conformance/canonical_contract.json")],
        max_risk=0.55,
    )

    assert result["status"] == "NO_CANDIDATE"
    assert any("protected autonomous-control surface" in reason for row in result["rejected"] for reason in row["reasons"])


def test_select_candidate_rejects_non_patch_actions_and_malformed_diffs(tmp_path: Path, monkeypatch):
    seed_repo(tmp_path)
    install_test_attestation(monkeypatch)

    non_patch = patch_proposal.make_patch_proposal(kind="run_test")
    malformed = patch_proposal.make_patch_proposal()
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
    proposal = patch_proposal.make_patch_proposal()
    proposal["evidence_gain"] = float("nan")

    result = patch_proposal.select_candidate(
        tmp_path,
        "e" * 40,
        [proposal],
        max_risk=0.55,
    )

    assert result["status"] == "NO_CANDIDATE"
    assert any("invalid-metric" in reason for row in result["rejected"] for reason in row["reasons"])

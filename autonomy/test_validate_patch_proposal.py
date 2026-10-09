import json
from pathlib import Path

import autonomy.validate_patch_proposal as verifier
from autonomy.patch_proposal import SCHEMA


def test_rejects_wrong_schema_and_non_proposal_status(tmp_path: Path):
    wrong = verifier.validate_artifact(tmp_path, {"schema": "wrong", "status": "PROPOSED"}, head_sha="a")
    empty = verifier.validate_artifact(tmp_path, {"schema": SCHEMA, "status": "NO_CANDIDATE"}, head_sha="a")
    assert wrong["status"] == "REJECTED"
    assert empty["status"] == "NO_CANDIDATE"


def test_rejects_stale_base_before_any_sandbox_execution(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(verifier, "select_candidate", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not run")))
    result = verifier.validate_artifact(
        tmp_path,
        {"schema": SCHEMA, "status": "PROPOSED", "base_sha": "old"},
        head_sha="new",
    )
    assert result["status"] == "STALE"


def test_rejects_artifact_when_source_proposal_digest_changes(tmp_path: Path):
    result = verifier.validate_artifact(
        tmp_path,
        {
            "schema": SCHEMA,
            "status": "PROPOSED",
            "base_sha": "a" * 40,
            "source_proposal": {"kind": "apply_patch"},
            "proposal_digest": "not-the-real-digest",
        },
        head_sha="a" * 40,
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "source-proposal-digest-mismatch"


def test_independently_revalidates_proposal_before_testing(tmp_path: Path, monkeypatch):
    proposal = {"kind": "apply_patch", "unified_diff": "diff"}
    digest = verifier.digest(proposal)
    artifact = {
        "schema": SCHEMA,
        "status": "PROPOSED",
        "base_sha": "a" * 40,
        "source_proposal": proposal,
        "proposal_digest": digest,
    }
    monkeypatch.setattr(
        verifier,
        "select_candidate",
        lambda root, head, rows, **kwargs: {
            "schema": SCHEMA,
            "status": "PROPOSED",
            "base_sha": head,
            "proposal_digest": digest,
            "unified_diff": "diff",
        },
    )

    result = verifier.validate_artifact(tmp_path, artifact, head_sha="a" * 40)
    assert result["status"] == "READY_FOR_TEST"


def test_validation_runs_in_disposable_worktree_and_records_evidence(tmp_path: Path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    proposal = {"kind": "apply_patch", "unified_diff": "diff"}
    digest = verifier.digest(proposal)
    input_path = tmp_path / "candidate.json"
    output_path = tmp_path / "validation.json"
    input_path.write_text(
        json.dumps({
            "schema": SCHEMA,
            "status": "PROPOSED",
            "base_sha": "a" * 40,
            "source_proposal": proposal,
            "proposal_digest": digest,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(verifier, "current_head", lambda repo_root: "a" * 40)
    monkeypatch.setattr(
        verifier,
        "select_candidate",
        lambda root, head, rows, **kwargs: {
            "schema": SCHEMA,
            "status": "PROPOSED",
            "base_sha": head,
            "proposal_digest": digest,
            "unified_diff": "diff",
        },
    )

    class FakeSimulation:
        status = "PASS"
        egress_blocked = True
        def as_dict(self):
            return {"status": self.status, "validation_returncode": 0, "egress_blocked": self.egress_blocked}

    class FakeWorktree:
        def __init__(self, repo_root):
            self.repo_root = repo_root
        def run(self, patch, command, **kwargs):
            assert patch == "diff"
            assert command == verifier.VALIDATION_COMMAND
            assert kwargs.get("require_egress_block") is True
            return FakeSimulation()

    monkeypatch.setattr(verifier, "DisposableWorktree", FakeWorktree)
    result = verifier.validate_and_test(root, input_path, output_path)

    assert result["status"] == "VALIDATED"
    assert result["validation_contract"]["model_api_keys_present"] is False
    assert result["validation_contract"]["repository_write_token_present"] is False
    assert result["validation_contract"]["egress_block_required"] is True
    assert result["validation_contract"]["egress_block_established"] is True
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "VALIDATED"



def test_validation_refuses_to_run_with_model_keys_or_write_token(tmp_path: Path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    input_path = tmp_path / "candidate.json"
    output_path = tmp_path / "validation.json"
    input_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CAIOS_CODEX_API_KEY", "must-not-be-visible-to-tests")
    monkeypatch.delenv("CAIOS_AUTOBUILD_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    result = verifier.validate_and_test(root, input_path, output_path)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "validation-job-credential-isolation-violated"
    assert result["model_api_key_environment_names"] == ["CAIOS_CODEX_API_KEY"]

from pathlib import Path
import json

from autonomy.slsa_provenance import PREDICATE_TYPE, build_provenance


def test_slsa_provenance_binds_repo_commit_and_subject(tmp_path: Path, monkeypatch):
    (tmp_path / "artifact.txt").write_text("hello", encoding="utf-8")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    result = build_provenance(tmp_path, ("artifact.txt",))
    assert result["_type"] == "https://in-toto.io/Statement/v1"
    assert result["predicateType"] == PREDICATE_TYPE
    assert result["subject"][0]["name"] == "artifact.txt"
    assert result["subject"][0]["digest"]["sha256"]
    assert result["predicate"]["runDetails"]["metadata"]["invocationId"] == "123"


def test_missing_subject_is_not_fabricated(tmp_path: Path):
    result = build_provenance(tmp_path, ("missing.bin",))
    assert result["subject"] == []

from pathlib import Path
import hashlib
import json

from autonomy.slsa_verifier import verify_statement, verify_file


def statement(subject_name, digest_value):
    return {
        "_type":"https://in-toto.io/Statement/v1",
        "subject":[{"name":subject_name,"digest":{"sha256":digest_value}}],
        "predicateType":"https://slsa.dev/provenance/v1",
        "predicate":{
            "buildDefinition":{"buildType":"test"},
            "runDetails":{"builder":{"id":"test"}}
        }
    }


def test_slsa_statement_verifies_subject_digest(tmp_path: Path):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("hello", encoding="utf-8")
    digest_value = hashlib.sha256(artifact.read_bytes()).hexdigest()
    ok, errors = verify_statement(
        statement("artifact.txt", digest_value),
        subject_paths={"artifact.txt": artifact},
    )
    assert ok is True
    assert errors == []


def test_slsa_statement_detects_subject_mismatch(tmp_path: Path):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("hello", encoding="utf-8")
    ok, errors = verify_statement(
        statement("artifact.txt", "0"*64),
        subject_paths={"artifact.txt": artifact},
    )
    assert ok is False
    assert "subject-sha256-mismatch:artifact.txt" in errors


def test_slsa_file_verifier_round_trip(tmp_path: Path):
    path = tmp_path / "statement.json"
    row = statement("artifact", "a"*64)
    path.write_text(json.dumps(row), encoding="utf-8")
    ok, errors = verify_file(path)
    assert ok is True
    assert errors == []

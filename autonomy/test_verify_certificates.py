import json
from pathlib import Path

from autonomy.caios_runtime import DecisionCertificate, Evidence, write_certificates
from autonomy.verify_certificates import verify


def _certificate(session_id="session-1", anchor="anchor-1"):
    return DecisionCertificate(
        cycle=1,
        selected_action=None,
        decision="HALT",
        score=0.0,
        gaps_before={"conformance": 1.0},
        evidence=(
            Evidence(
                "session-anchor",
                "PASS",
                "test",
                anchor,
                {"session_id": session_id},
            ),
        ),
        reasons=("blocked",),
        action_fingerprint=None,
        previous_certificate_digest=None,
        elapsed_ms=1,
        session_id=session_id,
        session_anchor_hash=anchor,
    )


def test_certificate_with_session_anchor_verifies(tmp_path: Path):
    path = tmp_path / "certificates.jsonl"
    write_certificates([_certificate()], path)
    ok, errors = verify(path)
    assert ok is True
    assert errors == []


def test_certificate_without_anchor_is_rejected(tmp_path: Path):
    path = tmp_path / "certificates.jsonl"
    cert = _certificate()
    row = cert.as_dict()
    row["evidence"] = []
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    ok, errors = verify(path)
    assert ok is False
    assert any("session anchor missing" in error for error in errors)


def test_certificate_chain_cannot_change_session(tmp_path: Path):
    first = _certificate("session-1", "anchor-1")
    second = _certificate("session-2", "anchor-2")
    second = DecisionCertificate(
        **{
            **second.as_dict(),
            "proof_digest": None,
        }
    )
    second_row = second.as_dict()
    # Recompute proof using the object shape by removing the generated seal.
    second_row.pop("proof_digest", None)
    second = DecisionCertificate(
        cycle=second_row["cycle"],
        selected_action=second_row["selected_action"],
        decision=second_row["decision"],
        score=second_row["score"],
        gaps_before=second_row["gaps_before"],
        evidence=tuple(Evidence(**e) for e in second_row["evidence"]),
        reasons=tuple(second_row["reasons"]),
        action_fingerprint=second_row["action_fingerprint"],
        previous_certificate_digest=first.proof_digest,
        elapsed_ms=second_row["elapsed_ms"],
        observation_digest=None,
        council_digest=None,
        session_id="session-2",
        session_anchor_hash="anchor-2",
    )
    path = tmp_path / "certificates.jsonl"
    write_certificates([first, second], path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[1]["previous_certificate_digest"] = first.proof_digest
    # Preserve the second proof seal after the previous-link edit.
    rows[1]["proof_digest"] = second.proof_digest
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    ok, errors = verify(path)
    assert ok is False
    assert any("session_id changed" in error for error in errors)

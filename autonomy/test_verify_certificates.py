import json
from pathlib import Path

from autonomy.caios_runtime import DecisionCertificate, Evidence, digest, write_certificates
from autonomy.verify_certificates import verify


def _certificate(session_id="session-1", anchor="anchor-1", previous=None, cycle=1):
    return DecisionCertificate(
        cycle=cycle,
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
        previous_certificate_digest=previous,
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
    first = _certificate("session-1", "anchor-1", cycle=1)
    second = _certificate(
        "session-2",
        "anchor-2",
        previous=digest(first.as_dict()),
        cycle=2,
    )

    path = tmp_path / "certificates.jsonl"
    write_certificates([first, second], path)

    ok, errors = verify(path)
    assert ok is False
    assert any("session_id changed" in error for error in errors)

from pathlib import Path
import json

from autonomy.evidence_ledger import EvidenceLedger, verify


class E:
    def __init__(self, kind, status, source, digest_value, details):
        self.kind=kind
        self.status=status
        self.source=source
        self.digest_value=digest_value
        self.details=details
    def as_dict(self):
        return {
            "kind": self.kind,
            "status": self.status,
            "source": self.source,
            "digest": self.digest_value,
            "details": self.details,
        }


def test_evidence_ledger_is_hash_chained(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    ledger = EvidenceLedger(path)
    events = ledger.append(
        1,
        [
            E("test","PASS","pytest","a"*64,{"n":1}),
            E("security","PASS","scanner","b"*64,{"n":2}),
        ],
    )
    assert len(events) == 2
    assert events[1].previous_event_digest == events[0].event_digest
    assert verify(path) == (True, [])


def test_evidence_ledger_detects_tampering(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    ledger = EvidenceLedger(path)
    ledger.append(1, [E("test","PASS","pytest","a"*64,{})])
    row = json.loads(path.read_text().splitlines()[0])
    row["status"] = "FAIL"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    ok, errors = verify(path)
    assert ok is False
    assert any("event-digest-mismatch" in error for error in errors)

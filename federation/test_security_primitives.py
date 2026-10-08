import pytest

from federation.node_identity import Ed25519PrivateKey, generate_identity
from federation.security_primitives import (
    AuditRecord,
    ManifestSealer,
    SessionAnchor,
    SessionAnchorRegistry,
    object_digest,
    sign_audit_record,
    verify_audit_record,
)


def test_session_anchor_rejects_replay_and_nonmonotonic_epoch(tmp_path):
    store = SessionAnchorRegistry(tmp_path / "anchors.jsonl")
    first = SessionAnchor.create("s1", 1, object_digest({"state": 1}))
    second = SessionAnchor.create("s1", 2, object_digest({"state": 2}))

    assert store.accept(first) == (True, "accepted")
    assert store.accept(first)[0] is False
    assert store.accept(second) == (True, "accepted")
    assert store.accept(SessionAnchor.create("s1", 2, object_digest({"state": 3})))[0] is False


def test_manifest_seal_detects_mutation():
    manifest = {"schema": "test/v1", "policy": ["a", "b"]}
    seal = ManifestSealer.seal(manifest)
    assert ManifestSealer.verify(manifest, seal) == (True, "verified")

    changed = {"schema": "test/v1", "policy": ["a", "changed"]}
    ok, reason = ManifestSealer.verify(changed, seal)
    assert ok is False
    assert reason == "manifest-digest-mismatch"


def test_signed_audit_record_verifies():
    if Ed25519PrivateKey is None:
        pytest.skip("optional cryptography dependency not installed")

    identity, private_key = generate_identity()
    payload = {"event": "session-open", "anchor": "abc"}
    record = sign_audit_record(
        "record-1",
        1,
        "SessionOpened",
        payload,
        identity,
        private_key,
    )
    ok, reason = verify_audit_record(record, payload, identity)
    assert ok is True
    assert reason == "verified"

    bad_payload = {"event": "session-open", "anchor": "changed"}
    ok, reason = verify_audit_record(record, bad_payload, identity)
    assert ok is False
    assert reason == "audit-payload-digest-mismatch"

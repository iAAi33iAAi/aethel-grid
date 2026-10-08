import pytest

from federation.node_identity import Ed25519PrivateKey, generate_identity
from federation.signed_envelope import build_envelope, verify_envelope_payload


def test_signed_federation_envelope_verifies_and_detects_tamper():
    if Ed25519PrivateKey is None:
        pytest.skip("optional cryptography dependency not installed")

    identity, private_key = generate_identity()
    envelope = build_envelope(identity, private_key, {"event": "announce", "tip": "abc"})

    ok, reason = verify_envelope_payload(envelope)
    assert ok is True
    assert reason == "verified"

    tampered = dict(envelope)
    tampered["payload"] = {"event": "announce", "tip": "changed"}
    ok, reason = verify_envelope_payload(tampered)
    assert ok is False
    assert reason == "payload-digest-mismatch"


def test_signed_envelope_rejects_public_key_identity_mismatch():
    if Ed25519PrivateKey is None:
        pytest.skip("optional cryptography dependency not installed")

    identity, private_key = generate_identity()
    envelope = build_envelope(identity, private_key, {"x": 1})
    envelope["node_id"] = "0" * 64

    ok, reason = verify_envelope_payload(envelope)
    assert ok is False
    assert reason == "node-id-fingerprint-mismatch"

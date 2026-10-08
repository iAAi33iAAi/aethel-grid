import pytest

from federation import node_identity


def test_ed25519_identity_round_trip():
    if node_identity.Ed25519PrivateKey is None:
        pytest.skip("optional cryptography dependency not installed")

    identity, private_key = node_identity.generate_identity()
    message = b"caios federation message"
    signature = node_identity.sign_envelope(private_key, message)

    assert len(identity.node_id) == 64
    assert node_identity.verify_envelope(identity, message, signature)
    assert not node_identity.verify_envelope(identity, b"tampered", signature)


def test_node_id_is_public_key_fingerprint():
    raw = b"public-key-material"
    identity = node_identity.NodeIdentity.from_public_key(raw)
    assert identity.node_id == node_identity.public_key_fingerprint(raw)

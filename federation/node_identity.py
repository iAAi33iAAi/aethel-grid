#!/usr/bin/env python3
"""
CAIOS federated Ed25519 identity adapter.

Optional dependency: pyca/cryptography.
This adapter does not auto-generate keys or transmit private material.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass


try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
except ImportError:  # pragma: no cover - availability depends on deployment profile
    serialization = None
    Ed25519PrivateKey = None
    Ed25519PublicKey = None


def _require_crypto() -> None:
    if Ed25519PrivateKey is None or Ed25519PublicKey is None or serialization is None:
        raise RuntimeError("Ed25519 adapter requires the optional 'cryptography' package")


def public_key_fingerprint(public_key_bytes: bytes) -> str:
    return hashlib.sha256(public_key_bytes).hexdigest()


@dataclass(frozen=True)
class NodeIdentity:
    node_id: str
    public_key_b64: str

    @property
    def public_key_bytes(self) -> bytes:
        return base64.b64decode(self.public_key_b64.encode("ascii"), validate=True)

    @classmethod
    def from_public_key(cls, public_key_bytes: bytes) -> "NodeIdentity":
        return cls(
            node_id=public_key_fingerprint(public_key_bytes),
            public_key_b64=base64.b64encode(public_key_bytes).decode("ascii"),
        )


def generate_identity() -> tuple[NodeIdentity, bytes]:
    _require_crypto()
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return NodeIdentity.from_public_key(public_bytes), private_bytes


def sign_envelope(private_key_bytes: bytes, message: bytes) -> str:
    _require_crypto()
    private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    signature = private_key.sign(message)
    return base64.b64encode(signature).decode("ascii")


def verify_envelope(identity: NodeIdentity, message: bytes, signature_b64: str) -> bool:
    _require_crypto()
    public_key = Ed25519PublicKey.from_public_bytes(identity.public_key_bytes)
    try:
        public_key.verify(
            base64.b64decode(signature_b64.encode("ascii"), validate=True),
            message,
        )
        return True
    except (ValueError, TypeError):
        return False

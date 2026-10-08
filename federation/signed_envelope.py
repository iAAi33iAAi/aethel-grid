#!/usr/bin/env python3
"""
CAIOS signed federation envelope.

Envelope fields are canonicalized before signing so every node can reproduce
the same signed bytes. Verification checks protocol, node identity, payload
digest, and signature.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from federation.node_identity import NodeIdentity, sign_envelope, verify_envelope


PROTOCOL = "caios-federation-envelope/v1"


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def payload_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def signing_material(node_id: str, payload: dict[str, Any]) -> bytes:
    return canonical_json(
        {
            "protocol": PROTOCOL,
            "node_id": node_id,
            "payload_sha256": payload_digest(payload),
            "payload": payload,
        }
    )


def build_envelope(
    identity: NodeIdentity,
    private_key_bytes: bytes,
    payload: dict[str, Any],
) -> dict[str, Any]:
    material = signing_material(identity.node_id, payload)
    return {
        "protocol": PROTOCOL,
        "node_id": identity.node_id,
        "public_key_b64": identity.public_key_b64,
        "payload_sha256": payload_digest(payload),
        "payload": payload,
        "signature_b64": sign_envelope(private_key_bytes, material),
    }


def verify_envelope_payload(envelope: dict[str, Any]) -> tuple[bool, str]:
    if envelope.get("protocol") != PROTOCOL:
        return False, "protocol-mismatch"

    node_id = str(envelope.get("node_id", ""))
    payload = envelope.get("payload")
    public_key_b64 = str(envelope.get("public_key_b64", ""))
    signature_b64 = str(envelope.get("signature_b64", ""))

    if not node_id or not isinstance(payload, dict) or not public_key_b64 or not signature_b64:
        return False, "envelope-fields-missing"

    try:
        identity = NodeIdentity(node_id=node_id, public_key_b64=public_key_b64)
        if identity.node_id != hashlib.sha256(identity.public_key_bytes).hexdigest():
            return False, "node-id-fingerprint-mismatch"
        if envelope.get("payload_sha256") != payload_digest(payload):
            return False, "payload-digest-mismatch"
        material = signing_material(identity.node_id, payload)
        if not verify_envelope(identity, material, signature_b64):
            return False, "signature-invalid"
    except Exception as exc:
        return False, f"verification-error:{type(exc).__name__}"

    return True, "verified"

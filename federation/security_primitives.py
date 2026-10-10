#!/usr/bin/env python3
"""
CAIOS federation security primitives.

Implements generic, source-independent building blocks for:
- monotonic session anchors / replay detection
- immutable KernelManifest-style seals
- Ed25519 audit-record signing

These primitives do not claim PFP conformance. They provide the machinery
required to build and verify those invariants without inventing missing
protocol semantics.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from federation.node_identity import NodeIdentity, sign_envelope, verify_envelope


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def object_digest(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


@dataclass(frozen=True)
class SessionAnchor:
    session_id: str
    epoch: int
    state_digest: str
    anchor_hash: str

    @classmethod
    def create(cls, session_id: str, epoch: int, state_digest: str) -> "SessionAnchor":
        material = {
            "session_id": session_id,
            "epoch": int(epoch),
            "state_digest": state_digest,
        }
        return cls(
            session_id=session_id,
            epoch=int(epoch),
            state_digest=state_digest,
            anchor_hash=object_digest(material),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "epoch": self.epoch,
            "state_digest": self.state_digest,
            "anchor_hash": self.anchor_hash,
        }


class SessionAnchorRegistry:
    """Append-only session registry enforcing uniqueness and monotonic epochs."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> list[SessionAnchor]:
        if not self.path.is_file():
            return []
        rows: list[SessionAnchor] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            rows.append(
                SessionAnchor(
                    session_id=str(item["session_id"]),
                    epoch=int(item["epoch"]),
                    state_digest=str(item["state_digest"]),
                    anchor_hash=str(item["anchor_hash"]),
                )
            )
        return rows

    def accept(self, anchor: SessionAnchor) -> tuple[bool, str]:
        expected = SessionAnchor.create(
            anchor.session_id,
            anchor.epoch,
            anchor.state_digest,
        )
        if expected.anchor_hash != anchor.anchor_hash:
            return False, "anchor-hash-mismatch"

        rows = self._read()
        same_session = [row for row in rows if row.session_id == anchor.session_id]
        if same_session:
            highest = max(row.epoch for row in same_session)
            if anchor.epoch <= highest:
                return False, "session-replay-or-nonmonotonic-epoch"

        duplicate_hash = any(row.anchor_hash == anchor.anchor_hash for row in rows)
        if duplicate_hash:
            return False, "anchor-replay"

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(anchor.as_dict(), sort_keys=True) + "\n")
        return True, "accepted"


@dataclass(frozen=True)
class ManifestSeal:
    manifest_digest: str
    schema: str
    signer_node_id: str | None
    signature_b64: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "manifest_digest": self.manifest_digest,
            "signer_node_id": self.signer_node_id,
            "signature_b64": self.signature_b64,
        }


class ManifestSealer:
    SCHEMA = "caios-manifest-seal/v1"

    @classmethod
    def seal(
        cls,
        manifest: dict[str, Any],
        identity: NodeIdentity | None = None,
        private_key_bytes: bytes | None = None,
    ) -> ManifestSeal:
        manifest_digest = object_digest(manifest)
        material = canonical_json(
            {
                "schema": cls.SCHEMA,
                "manifest_digest": manifest_digest,
            }
        )
        signature = None
        signer_node_id = None
        if identity is not None and private_key_bytes is not None:
            signature = sign_envelope(private_key_bytes, material)
            signer_node_id = identity.node_id
        return ManifestSeal(
            manifest_digest=manifest_digest,
            schema=cls.SCHEMA,
            signer_node_id=signer_node_id,
            signature_b64=signature,
        )

    @classmethod
    def verify(
        cls,
        manifest: dict[str, Any],
        seal: ManifestSeal,
        identity: NodeIdentity | None = None,
    ) -> tuple[bool, str]:
        if seal.schema != cls.SCHEMA:
            return False, "seal-schema-mismatch"
        observed = object_digest(manifest)
        if observed != seal.manifest_digest:
            return False, "manifest-digest-mismatch"
        if seal.signature_b64:
            if identity is None:
                return False, "signer-identity-required"
            if seal.signer_node_id != identity.node_id:
                return False, "signer-identity-mismatch"
            material = canonical_json(
                {
                    "schema": cls.SCHEMA,
                    "manifest_digest": seal.manifest_digest,
                }
            )
            if not verify_envelope(identity, material, seal.signature_b64):
                return False, "manifest-signature-invalid"
        return True, "verified"


@dataclass(frozen=True)
class AuditRecord:
    record_id: str
    epoch: int
    event_type: str
    payload_digest: str
    node_id: str
    signature_b64: str

    def signing_material(self) -> bytes:
        return canonical_json(
            {
                "record_id": self.record_id,
                "epoch": self.epoch,
                "event_type": self.event_type,
                "payload_digest": self.payload_digest,
                "node_id": self.node_id,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "epoch": self.epoch,
            "event_type": self.event_type,
            "payload_digest": self.payload_digest,
            "node_id": self.node_id,
            "signature_b64": self.signature_b64,
        }


def sign_audit_record(
    record_id: str,
    epoch: int,
    event_type: str,
    payload: dict[str, Any],
    identity: NodeIdentity,
    private_key_bytes: bytes,
) -> AuditRecord:
    payload_digest = object_digest(payload)
    unsigned = AuditRecord(
        record_id=record_id,
        epoch=int(epoch),
        event_type=event_type,
        payload_digest=payload_digest,
        node_id=identity.node_id,
        signature_b64="",
    )
    signature = sign_envelope(private_key_bytes, unsigned.signing_material())
    return AuditRecord(
        **{
            **unsigned.as_dict(),
            "signature_b64": signature,
        }
    )


def verify_audit_record(
    record: AuditRecord,
    payload: dict[str, Any],
    identity: NodeIdentity,
) -> tuple[bool, str]:
    if identity.node_id != record.node_id:
        return False, "node-identity-mismatch"
    if object_digest(payload) != record.payload_digest:
        return False, "audit-payload-digest-mismatch"
    if not verify_envelope(identity, record.signing_material(), record.signature_b64):
        return False, "audit-signature-invalid"
    return True, "verified"

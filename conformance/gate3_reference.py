#!/usr/bin/env python3
"""Reference implementation of the SPEC-004 Gate-3 integer law."""

from __future__ import annotations

import hashlib


def qdiv(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    quotient = abs(numerator) // denominator
    return -quotient if numerator < 0 else quotient


def split_transfer(gross: int) -> tuple[int, int, int]:
    if gross < 0:
        raise ValueError("gross must be non-negative")
    arch = qdiv(gross, 100)
    remainder = gross - arch
    comm = qdiv(remainder, 2)
    node = remainder - comm
    assert arch + comm + node == gross
    return arch, comm, node


def canonical_preimage(
    seq: str,
    from_id: str,
    to_node: str,
    gross: int,
    arch: int,
    comm: int,
    node: int,
    state_hash: str,
    timestamp: str,
    prev_hash: str,
) -> bytes:
    fields = [
        str(seq), str(from_id), str(to_node), str(gross), str(arch),
        str(comm), str(node), str(state_hash), str(timestamp), str(prev_hash),
    ]
    if any(":" in field for field in fields):
        raise ValueError("FIELD_DELIMITER_COLLISION")
    return ":".join(fields).encode("utf-8")


def sha256_hex(preimage: bytes) -> str:
    return hashlib.sha256(preimage).hexdigest()

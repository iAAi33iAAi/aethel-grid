# SPEC-004 Gate 3 — Cross-Substrate Arithmetic and Ledger Preimage Law

Status: **REFERENCE LAW LANDED / CROSS-IMPLEMENTATION LOCK PENDING**

## Integer arithmetic

All economic/ledger split arithmetic governed by this law uses signed integer division that truncates toward zero.

Let:

- `gross` be the integer gross transfer amount.
- `arch = qdiv(gross, 100)`.
- `remainder = gross - arch`.
- `comm = qdiv(remainder, 2)`.
- `node = remainder - comm`.

No floating-point arithmetic is permitted in these calculations.

The same operation must produce identical signed integer outputs in Rust, Python, and TypeScript/JavaScript BigInt implementations.

## Ledger hash preimage

The intended canonical field order is exactly ten fields:

`SEQ:FROM:TO_NODE:GROSS:ARCH:COMM:NODE:STATE_HASH:TIMESTAMP:PREV_HASH`

The digest is SHA-256 over the exact UTF-8 bytes of that preimage.

## Serialization invariant

Every implementation must:

1. construct the fields in exactly the order above;
2. use the same textual representation for every field;
3. reject delimiter collisions rather than silently changing field boundaries;
4. hash the exact UTF-8 bytes emitted by the canonical serializer;
5. compare the resulting SHA-256 digest byte-for-byte with the shared golden vector.

### Current closure boundary

The arithmetic law is fully specified here.

The ten-field preimage contract still has one unresolved normative detail: a colon-delimited grammar cannot safely carry an ISO-8601 timestamp such as `2026-10-07T12:00:00Z` without an escaping rule or a colon-free timestamp encoding. Until the canonical timestamp representation/escaping rule is ratified, the hash-preimage portion of Gate 3 must remain fail-closed.

This file deliberately does not invent that missing rule.

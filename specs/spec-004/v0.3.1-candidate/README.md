# SPEC-004 v0.3.1 Metric Law — Candidate Import for Review

**Status: CANDIDATE / NONCANONICAL / PROMOTION HOLD.**

This directory imports the recovered SPEC-004:v0.3.1_METRIC_LAW artifact into a separately versioned candidate directory. It does not change the existing SPEC-004 candidate package or canonical gate ledger.

## Contents

- SPEC-004_v0.3.1_METRIC_LAW.md: recovered law text.
- spec004_v031_metric_law.py: recovered Python reference, preserved for provenance.
- reference_kernel.py: defensive candidate adapter with strict integer types, signed i64/i128 bounds, six-domain shape checks, density bounds, transform allowlisting, metric-domain checking, ordered audit schema, and float rejection in the audit hash domain.
- golden_corpus.json: reconstructed four-vector corpus. The whole-file hash is not claimed to match the PDF-embedded original; each reconstructed audit preimage and preserved per-vector SHA-256 match.
- archived_test_metric_law.py: recovered dynamic derivation runner.
- test_reference_kernel.py and test_provenance.py: Python regression and provenance checks.
- rust/: independent Rust metric/decision derivation, canonical JSON serialization, SHA-256 checks, four corpus tests, and adverse-input tests.
- rust/Cargo.lock: locked crate versions and checksums.
- AMENDMENT_MANIFEST.json: artifact and corpus provenance.
- golden_corpus_v0.3_RIGOR_DEPRECATED.md: marks the older metrics as historical only.

## Run locally

From this directory:

    python archived_test_metric_law.py
    python -m unittest discover -s . -p 'test_*.py' -v
    cargo check --manifest-path rust/Cargo.toml --locked
    cargo test --manifest-path rust/Cargo.toml --locked
    cargo run --manifest-path rust/Cargo.toml --locked

CI pins the Rust toolchain action to an immutable commit, specifies rustc 1.99.0, and uses Cargo.lock with --locked so dependency resolution cannot silently change during verification.

## Deliberate limits

This package is a separate v0.3.1 candidate. Do not mix its metric values or hashes with the older SPEC-004:v0.3_RIGOR corpus in Undermoon PR #6.

The adapter's stricter input profile is a candidate wrapper, not silently retroactive normative text. The exact semantic evidence cap remains unresolved; this adapter enforces i64 representability but does not invent a smaller cap.

The compact JSON audit preimage used by these vectors is not the ten-field colon-delimited ledger preimage described by the separate Gate 3 reference law. Those byte contracts remain distinct until their scopes and encodings are ratified.

The Rust candidate retains V_h, A_h, Delta, C, and u_raw in i128 rather than down-casting intermediate values to i64. A new high-boundary test exercises six i64::MAX evidence values, whose V_h and Delta exceed i64 but remain within i128. Both languages test the same expected intermediate values. The Rust parser also rejects an empty transform list and denies unknown fields on typed corpus structures.

The tests do not prove production cryptographic signing, sensor truth, physical behavior, complete execution admission, formally verified arithmetic, independent external review, or Level-4 certification. Rust/Python matching the recorded vectors and explicit arithmetic boundary is a concrete candidate conformance result, not a general proof over every permitted input.

## Promotion rule

PROMOTION = HOLD until the responsible project authority explicitly ratifies the amendment, all normative input and overflow semantics are reviewed, further property/boundary tests pass, canonical Gate 3 timestamp/escaping semantics are resolved, and canonical gate records are updated from clean-checkout CI evidence.

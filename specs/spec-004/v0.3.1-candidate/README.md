# SPEC-004 v0.3.1 Metric Law — Candidate Import for Review

**Status: CANDIDATE / NONCANONICAL / PROMOTION HOLD.**

This directory imports the recovered SPEC-004:v0.3.1_METRIC_LAW artifact into a separately versioned candidate package. It does not change the existing SPEC-004 candidate package or canonical gate ledger.

## Contents

- SPEC-004_v0.3.1_METRIC_LAW.md: recovered law text.
- spec004_v031_metric_law.py: recovered Python reference, preserved for provenance.
- reference_kernel.py: defensive candidate adapter with strict integer types, signed i64/i128 bounds, six-domain shape checks, density bounds, transform allowlisting, strict metric-domain checking, ordered audit schema, and float rejection in the audit hash domain.
- golden_corpus.json: reconstructed four-vector corpus. The whole-file hash is not claimed to match the PDF-embedded original; each reconstructed audit preimage and preserved per-vector SHA-256 match.
- archived_test_metric_law.py: recovered dynamic derivation runner.
- test_reference_kernel.py and test_provenance.py: regression and provenance checks.
- AMENDMENT_MANIFEST.json: artifact and corpus provenance.
- golden_corpus_v0.3_RIGOR_DEPRECATED.md: marks the older metrics as historical only.

## Run locally

From this directory:

    python archived_test_metric_law.py
    python -m unittest discover -s . -p 'test_*.py' -v

## Deliberate limits

This package is a separate v0.3.1 candidate. Do not mix its metric values or hashes with the older SPEC-004:v0.3_RIGOR corpus in Undermoon PR #6.

The adapter's stricter input profile is a candidate wrapper, not silently retroactive normative text. The exact semantic evidence cap remains unresolved; this adapter enforces i64 representability but does not invent a smaller cap.

The compact JSON audit preimage used by these vectors is not the ten-field colon-delimited ledger preimage described by the separate Gate 3 reference law. Those byte contracts remain distinct until their scopes and encodings are ratified.

The tests do not prove Rust parity, production cryptographic signing, sensor truth, physical behavior, complete execution admission, or Level-4 certification.

## Promotion rule

PROMOTION = HOLD until the responsible project authority explicitly ratifies the amendment, Rust and Python agree from raw inputs through exact audit bytes and digests, domain/overflow cases pass, and canonical gate records are updated from clean-checkout CI evidence.

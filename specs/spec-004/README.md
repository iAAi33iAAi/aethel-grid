# SPEC-004 Candidate Conformance Package

Status: CANDIDATE_NONCANONICAL

This directory contains a deterministic candidate implementation of the requested
TV-001 through TV-007 suite. It is deliberately not presented as canonical.

The candidate suite is aligned to the semantics currently executable in
`interop/aethel_service.py` plus explicit policy boundary tests for quorum,
blast radius, non-finite metrics, and payload size.

## Contents

- `vectors/TV-001.json` through `TV-007.json`
- `validate_spec_004.py`

## Run

```bash
python3 specs/spec-004/validate_spec_004.py
```

A zero exit code means the candidate vectors agree with the candidate validator.

## Canonicality

Canonical promotion remains blocked until the authoritative golden-vector
semantics, schema, validator, and release process are ratified independently.

The validator therefore emits `canonical_promotion=BLOCKED_PENDING_EXTERNAL_RATIFICATION`
even when all seven candidate vectors pass.

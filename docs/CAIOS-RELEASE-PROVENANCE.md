# CAIOS Release Provenance Runbook

Routine CI establishes engineering evidence. Release CI establishes artifact provenance.

## Routine CI

Routine CAIOS runs should verify architecture tests, execute the bounded autonomy loop, verify decision certificates and the evidence ledger, seal the federation manifest, generate and verify the SLSA provenance Statement, and publish readiness/graph/directive/compliance reports.

Routine CI should not require release signing.

## Release CI

A release workflow should check out the exact release revision, repeat deterministic tests, create a reproducible bundle, generate the SLSA provenance Statement, create a cryptographically verifiable artifact attestation through the repository's approved attestation service, retain the attestation with release metadata, and verify it before promotion.

## in-toto relationship

CAIOS provenance uses the current in-toto Statement v1 structure: _type, subject, predicateType, and predicate. Subjects are bound by immutable digests.

## Verification boundary

External signing or transparency systems authenticate provenance. CAIOS consumes their results as evidence and never promotes the signer into execution authority.

## Canonical readiness

Valid artifact provenance is necessary but not sufficient for canonical system promotion. The authoritative SPEC-004 validator and required conformance vectors must still be established.

## Licensing boundary

Source-code licenses, model-weight licenses, protocol licenses, and hosted-service terms remain separate admission dimensions.
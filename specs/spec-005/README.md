# SPEC-005 Candidate: Knowledge Contract Envelope

**Status:** CANDIDATE_NONCANONICAL  
**Version:** candidate-0.1  
**Scope:** Structural contract for domain-bounded advisory intelligence. This package is not canonical SPEC-004, CPOL, an authorization grant, or proof of production deployment.

## Purpose

Define a machine-readable boundary between a domain specialist model and the system that governs it. A Knowledge Contract lists the approved model digests, domain, agent, evidence sources, sensors, targets, permitted recommendation types, telemetry freshness, evidence-quality floor, expiration, revocation flag, and policy identifier.

The contract is a constraint on a model's proposal space. It does not grant the model authority to execute an operation, move money, change infrastructure, or modify persistent state.

## Contents

- SPEC-005.schema.json — JSON Schema Draft 2020-12 for the signed envelope and Knowledge Contract fields.
- validate_spec_005.py — structural validator that cross-checks defensive invariants against the actual Draft 2020-12 JSON Schema using the `jsonschema` package.
- vectors/KC-001.json through KC-008.json — candidate shape and negative-case vectors.

## Validate

From the repository root:

    python3 specs/spec-005/validate_spec_005.py

A zero exit code means the candidate vectors agree with both the declared JSON Schema and the additional defensive validator, with no detected validator drift. It does not mean cryptographic signatures were verified or SPEC-005 was canonically ratified. The validator must print:

    canonical_promotion=BLOCKED_PENDING_EXTERNAL_RATIFICATION

## Signed-envelope profile under evaluation

The envelope contains a Knowledge Contract, signer key ID, UTC issue time, explicit Ed25519 algorithm, and base64 signature field with the Ed25519 signature length. Issuer trust is external: the envelope cannot supply its own trusted key.

The vector signatures are intentionally dummy values. They test field shape and encoding only; cryptographic verification must reject them. validate_spec_005.py deliberately reports cryptographic_verification=NOT_PERFORMED_BY_THIS_VALIDATOR.

The Colony MVD-001 implementation currently verifies Ed25519 signatures against a host-configured trust-anchor map and binds advisory decision records to a normalized contract digest. Its deterministic JSON profile is project-local. This candidate package does not yet ratify a cross-language signing payload, revocation service, or canonical serialization standard.

## Required ratification gates

1. Agree the normative schema, field semantics, identifier rules, timestamps, defaults, and unknown-field behavior.
2. Ratify a cross-language canonicalization and signature-payload specification with valid and tampered signature vectors.
3. Define trust-anchor distribution, key rotation, durable revocation, expiry, rollback resistance, and audit requirements.
4. Define independent reference implementations and language-specific conformance tests.
5. Demonstrate that a proposal can never become execution authority merely by passing contract validation.
6. Ratify through the repository's explicit external review and release process.

Until these gates are met, this package must remain candidate/noncanonical. Passing its validator does not promote the specification or establish security certification.

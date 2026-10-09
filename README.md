# AETHEL Grid

**Deterministic Governance. Verifiable State. Human-Centered Infrastructure.**

AETHEL Grid is an open protocol and bootstrap implementation for systems where event history can be inspected, state can be reconstructed deterministically, and governance rules can be made explicit.

## Current repository status

| Component | Status |
|---|---|
| Bootstrap event algebra and interop service | Implemented |
| Bootstrap interop tests | Implemented |
| Candidate SPEC-004 TV-001 through TV-007 package | Implemented as candidate/non-canonical |
| Candidate SPEC-005 Knowledge Contract schema and KC-001 through KC-008 vectors | Implemented as candidate/non-canonical |
| Canonical SPEC-004 validator and ratified golden vectors | **Not yet established** |
| Multi-language canonical conformance | Pending canonical specification |
| Node 001 physical deployment | Not independently established here |

## Protocol model

The repository is centered on the event-sourcing model:

    STATE(G) = fold(topo_order(closure(G)))

The implementation in interop/aethel_service.py is explicitly a bootstrap reconstruction of that model.

Important boundary: the bootstrap service does not establish final canonical ordering semantics, cryptographic event signatures, canonical SPEC-004 conformance, or production federation certification.

Identical input to the bootstrap implementation produces deterministic output. That does not by itself prove the complete federated protocol or eliminate all privileged authority.

## Run the current implementation

Start the bootstrap service:

    python3 interop/aethel_service.py --host 127.0.0.1 --port 8103

The service exposes:

- GET /aethel/health
- GET /aethel/capabilities
- POST /aethel/evaluate

Run the candidate SPEC-004 validator:

    python3 specs/spec-004/validate_spec_004.py

A successful candidate-vector run does not promote SPEC-004 to canonical status.

## Repository structure

    interop/
      aethel_service.py
      test_aethel_service.py

    specs/spec-004/
      vectors/TV-001.json through TV-007.json
      SPEC-004.schema.json
      validate_spec_004.py
      README.md

    .github/workflows/

## Why it matters

AETHEL explores infrastructure in which event history is explicit, state reconstruction is deterministic, governance rules can become executable, and evidence can be inspected independently.

These are engineering goals. They are not presented here as proof that the complete civilizational, federated, or physical architecture is already deployed or independently certified.

## Roadmap

### Phase 1 — Foundation
Bootstrap event algebra, candidate conformance package, tests, and CI.

### Phase 2 — Canonicalization
Ratify authoritative SPEC-004 semantics, schema, golden vectors, and an independent reference validator.

### Phase 3 — Multi-language conformance
Test additional implementations against the ratified vectors.

### Phase 4 — Pilot deployments
Validate real operational event flows against the canonical protocol.

### Phase 5 — Federation
Demonstrate multi-node synchronization and governance only after canonical semantics and security boundaries are independently verified.

## Founder

**John David Taylor Preston**
Founder-Architect | AETHEL Grid / Alpha Intelligence

## License

License selection pending. Contributions, protocol review, and discussion are welcome.
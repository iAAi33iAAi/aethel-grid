# CAIOS Federation Bridge

**License: Apache-2.0**

The Federation Bridge turns the AETHEL family of repositories into a single observable dependency graph.

It does not merge source trees. It does not copy third-party code. It records repository state, explicit dependency relationships, verification results, and a deterministic next-inspection priority.

## Constitutional Dependency Pressure

For each repository:

```
CDP(r) = weight(r) × (gap(r) + 2×failure(r)) × (1 + dependents(r))
         ---------------------------------------------------------
                    1 + verification_cost(r)
```

This prevents the autonomous controller from optimizing only the repository where it happens to be running. It can reason about the health of the whole system.

The bridge remains observation-only. Mutation continues to require the CAIOS constitutional gate.

## Local workspace

The default manifest expects:

```
aethel-grid/
federated/
  safety-kernel/
  project-mono/
  openclaw-governance/
  undermoon/
  alpha-intelligence-hub/
  World-Tribe-Protocol/
```

Populate those paths by cloning the public repositories into the declared locations.

## Run

```bash
python federation/caios_federation.py --verify
```

The snapshot is written to:

```
ops/caios/federation-snapshot.json
```


## Portfolio CI parity evidence

The manifest-driven parity auditor runs each repository's declared verifier and records the exact checked-out Git revision, command, source URL where declared, verification scope, result, duration, and bounded output.

Commands are argument arrays (never routed through a shell), receive a minimal environment and temporary home, and have bounded timeouts. Checkout credentials are not persisted into the repository verification process. These controls reduce accidental authority; they are not a formal sandbox for hostile tests.

The previous fully passing integrated baseline on PR #34 commit `8ace723193acc8262a2aa0b0aa3fc079ce88aad0` reported `PASS` for verification coverage: **13 of 13 verifiers passed, zero were unconfigured, and zero failed**. See [that exact-head audit run](https://github.com/iAAi33iAAi/aethel-grid/actions/runs/38003981219). The manifest now requires a non-empty `verification_scope` for every repository; the portfolio auditor preserves each scope in its evidence and rejects omitted scope declarations. Source links, where present, must be immutable GitHub blob URLs whose repository slug matches the corresponding manifest ID.

A `PASS` result means every declared command passed at the recorded revision. It does **not** mean every repository contains a complete executable runtime, has been deployed, or is production-conformant. The scope descriptions below are normative metadata for interpreting the evidence, not claims that the unimplemented systems exist.

### Declared verification scope

| Repository | What the configured verifier checks | What it does not establish |
|---|---|---|
| `aethel-grid` | Python `interop/` tests. | Canonical SPEC-004/CPOL ratification, all source-module behavior, or deployment. |
| `safety-kernel` | CLI, proof generation/verification, integrity, and tamper checks in `test_sk.py`. | Formal verification of host OS/hardware isolation or production certification. |
| `project-mono` | Declared pytest suite under `tests/`. | Live-service availability or successful deployments. |
| `openclaw-governance` | Five unit tests for sovereignty-flow predicates and compatibility singleton. | Complete agent orchestration or production deployment. |
| `openclaw-colony` | Two CAIOS Interop adapter/response-contract tests. | Full Colony suite, native Rust kernel, or production conformance. |
| `undermoon` | Existing CI-declared interop suite. | Full-system behavior, all external integrations, or deployment. |
| `alpha-intelligence-hub` | Four scaffold tests for the Compose target declarations, script syntax, and remote definitions. | Repository migration, working target services, image builds, or deployment readiness. |
| `World-Tribe-Protocol` | `scripts/test_worldtribe.py` contract/sidecar checks. | Live blockchain deployment, transaction finality, or external identity trust. |
| `sports-math-agent-orchestration` | Declared project tests under `tests/`. | Live-data freshness, deployment behavior, or production decision safety. |
| `calcula-colony` | Five design-document contract tests, including evaluation-weight arithmetic and historical-status disclosure. | An executable engine, runtime, payment protocol, or empirical/scientific law. |
| `crew-colony` | Five scaffold/documentation tests, including the MANNA allocation arithmetic. | An executable multi-agent runtime or agent behavior. |
| `clawhub` | ClawHub `ci:unit` unit/coverage command with locked dependencies. | Security of every third-party skill, publishing integrity, or every runtime integration. |
| `ALEXARAC` | Six concept-document and bill-of-materials checks. | A deployed application, physical engineering validation, pricing, regulatory approval, or field performance. |

Design/scaffold checks are valid verification of the repository's current documented deliverable, not proof that the proposed runtime or physical infrastructure exists. Gate closure must be interpreted at its declared level: CI verification coverage is separate from production conformance and from the unresolved SPEC-004/Gate 3/Gate 4 requirements.

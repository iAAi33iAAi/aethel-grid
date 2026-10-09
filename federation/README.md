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

The CAIOS federated audit also runs the portfolio parity auditor:

    python federation/portfolio_ci_parity.py --manifest federation/system_manifest.json --root . --output ops/caios/portfolio-ci-parity.json

The report identifies each repository's checked-out Git commit and runs only the verifier declared in federation/system_manifest.json. Commands are argument arrays and are not sent through a shell. The audit uses a minimal environment, a temporary home directory, and a bounded timeout. The federation workflow disables persisted checkout credentials before any declared test command can run.

Portfolio status is conservative:

- PASS: every repository has a verifier and each verifier passed at the recorded commit.
- PARTIAL: configured verifiers passed, but at least one repository has no verifier. PARTIAL is not portfolio-wide conformance.
- FAILED: a checkout, revision, manifest, command, or verification failed.

The latest successful main-branch audit on commit `241887de807dd5d94df87936ac357a35a7ff6d78` configured nine of thirteen manifest entries with explicit verification commands; four are reported `NOT_CONFIGURED`, and none of the configured verifiers failed. The report records each repository's checked-out commit, command, and source where declared. See [the main-branch audit run](https://github.com/iAAi33iAAi/aethel-grid/actions/runs/38000629663). The overall result remains `PARTIAL`, and Gate 5 remains `PARTIALLY_CLOSED`.

One verifier is deliberately scoped: OpenClaw Colony's `tests/test_caios_interop.py` returned 2 passed and checks only its CAIOS adapter fallback and AETHEL Interop v1 response contract. It does not represent the full Colony test suite, native Rust kernel, or production conformance.

### Remaining unconfigured repositories

| Repository | Verified blocker | Evidence needed before adding a passing verifier |
|---|---|---|
| `alpha-intelligence-hub` | The README describes a migration scaffold whose Compose file points to source directories not present in the current tree. Its current CI workflow refers to missing test/source paths. | Restore the assembled tree or provide actual root-level implementations, then make CI run a real build/test command. |
| `calcula-colony` | The README describes a research/design package with essays, whitepaper, roadmap, attribution, and licenses; no executable engine or tests are present. | Implement the engine and schemas with reproducible tests, or formally classify this entry as a non-executable design artifact. |
| `crew-colony` | The README says the current tree has only package initializers, README, and license; the claimed runtime and suite are absent. | Add the actual runtime and regression tests before configuring a verifier. Empty test discovery is not acceptable evidence. |
| `ALEXARAC` | The README explicitly calls this a concept/interface specification and says no application, backend source tree, or web runtime is shipped. | Supply the application/backend implementation and tests, or classify it as a design-only dependency rather than executable software. |

These four repositories remain `NOT_CONFIGURED`; their design documentation is not counted as a software test pass. Gate 5 cannot be declared closed until every active dependency has an appropriate, passing verifier and the evidence scope is stated clearly.

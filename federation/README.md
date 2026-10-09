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

The latest passing integrated audit on PR #32 candidate commit `40afbfbb61f85131298afd5bd3df911a4503e032` reported `PASS` for verification coverage: all 13 manifest repositories had an explicit verifier, all 13 passed, and zero verifiers were missing or failed. See [the exact-candidate audit run](https://github.com/iAAi33iAAi/aethel-grid/actions/runs/38002331255). The audit records each checked-out repository commit, executed command, result, and declared verifier source. Source URLs in the manifest are pinned to immutable Git commit SHAs so a later branch update cannot silently change which workflow or test file is being cited.

**Interpretation boundary:** `PASS` means every declared verifier passed at the recorded revision. It does not imply that every repository ships a complete runtime or is production-conformant. Scope-limited verifiers check the actual current deliverable and explicitly document what remains unimplemented.

### Explicitly scoped verification

| Repository | What the passing verifier establishes | What it does not establish |
|---|---|---|
| `openclaw-colony` | Two CAIOS Interop adapter/response-contract tests pass. | Full Colony suite, native Rust kernel, or production conformance. |
| `alpha-intelligence-hub` | Four tests verify the existing scaffold, migration-script syntax, Compose target declarations, and remote definitions. | Repository migration execution, working target services, image builds, or deployment readiness. |
| `calcula-colony` | Five tests verify design-document integrity, evaluation-weight arithmetic, attribution, and historical-status disclosure. | Executable engine, runtime, payment protocol, or empirical/scientific law. |
| `crew-colony` | Five tests verify the documentation scaffold and MANNA allocation arithmetic. | Executable multi-agent runtime or agent behavior. |
| `ALEXARAC` | Six tests verify concept artifacts, BOM disclosures, and procurement/engineering caveats. | A deployed application, physical engineering, prices, regulatory approval, or field performance. |

These limits are evidence, not hidden exceptions. A future implementation changes the repository's scope only when source code and its own repeatable verification are added.

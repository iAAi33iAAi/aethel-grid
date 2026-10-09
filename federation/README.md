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

The latest passing audit on commit `536067422787de62351227f1b50e55d33c09e05e` configured six of the thirteen manifest entries with explicit verification commands; seven are reported `NOT_CONFIGURED`, and none of the configured verifiers failed. The report records each repository's exact checked-out commit, command, and (where supplied) HTTPS verifier source. See [the audit run](https://github.com/iAAi33iAAi/aethel-grid/actions/runs/37999299149). The portfolio result remains `PARTIAL`, and Gate 5 remains `PARTIALLY_CLOSED` until every active repository has an appropriate verifier and passing evidence. Documentation-only or incomplete repositories must not be counted as proof of executable system conformance.

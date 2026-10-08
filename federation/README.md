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

# CAIOS Autonomous Directive

## Purpose

CAIOS is the coordination/control plane for AETHEL's bounded autonomous operation. It does not make an autonomous system trustworthy merely by adding a language model; it makes execution conditional on deterministic policy and observable evidence.

## State transition

At cycle t:

- Observe repository state and declared federated dependencies.
- Compute evidence set E_t and gap vector g_t.
- Deliberate with bounded advisory agents to produce normalized priorities p_t.
- Generate candidate actions C_t from deterministic baselines plus optional model proposals.
- Apply constitutional gate G(a, S_t).
- Rank surviving actions with the viability function V(a) and bounded council multiplier.
- Execute only an allowed action through an explicit argv/tool boundary.
- Re-observe the result.
- Emit certificate K_t and proof graph P_t.
- Continue only when the resulting state remains within policy.

The deterministic selection law is:

V(a) =
  ((4G_a + 3E_a + 2R_a) / (1 + 5Risk_a + 2Cost_a))
  * (1 + 0.35 * CouncilPriority_gap(a))

All normalized action metrics are constrained to [0,1].

CouncilPriority is advisory only. The constitutional gate is authoritative.

## Proof law

Each certificate contains:

- observation digest
- council digest
- selected action fingerprint
- evidence digests and statuses
- previous certificate digest
- proof digest

The proof seal is:

K_t = SHA256(canonical_json(
  cycle,
  action,
  decision,
  gaps,
  evidence,
  reasons,
  action_fingerprint,
  K_(t-1),
  observation_digest,
  council_digest
))

The verifier recomputes K_t and the previous-certificate link. A modified certificate therefore becomes detectable.

## Mutation law

Model-generated mutation is not privileged.

An autonomous patch must:

1. pass the constitutional action gate;
2. remain inside the repository root;
3. stay within the change budget;
4. start from a clean working tree;
5. pass git apply --check;
6. apply successfully;
7. pass a deterministic validation suite;
8. roll back when validation fails.

The model cannot sign, authorize, or silently promote its own output.

## Conformance law

SPEC-004 is not reconstructed from memory or inferred from legacy validators.

A canonical conformance PASS requires repository-owned authoritative material:

- declared canonical validator path and command;
- hash anchor for the validator;
- TV-001 through TV-007 declarations;
- paths and hash anchors for every required vector;
- declared canonical encoding semantics;
- declared audit-preimage semantics;
- explicit anti-promotion rule preventing bootstrap semantics from becoming canonical.

Until those are present and internally verified, CAIOS returns BLOCKED.

## Federation law

The federation manifest defines explicit repository nodes and directed dependencies. CAIOS computes Constitutional Dependency Pressure (CDP) so downstream failure can increase pressure on the upstream dependency capable of unblocking recovery.

Federation remains observation-only by default. Cross-repository mutation requires a separately declared authority boundary.

## Tool law

External frameworks are adapters, not hidden authorities. The tool registry records capability, authority class, and license/provenance requirements. A future adapter must:

- use an exact version or commit;
- preserve required license/NOTICE material;
- produce provenance/SBOM evidence for distributed builds;
- remain inside CAIOS policy;
- never obtain execution authority from model text alone.

## System objective

The runtime optimizes for evidence-producing progress under bounded risk:

maximize progress + evidence + reversibility
while minimizing risk + resource cost

subject to constitutional invariants, provenance requirements, and explicit execution authority.

This is a concrete engineering synthesis, not a claim that no prior system has ever used any individual component described above.


## Agent arbitration

External agents are workers, not constitutional authorities. Proposals are admitted only after registry-backed identity attestation. For actions above the high-risk threshold, CAIOS groups proposals by exact execution intent (kind, target, command, and patch contents) and requires the configured number of independent agent families to support that intent before the candidate can enter execution planning.

Agreement is therefore evidence about an action, not permission to bypass the gate. The gate, deterministic validation, and proof-carrying certificate remain authoritative.

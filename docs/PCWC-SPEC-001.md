# CAIOS Proof-Carrying Work Contract (PCWC) — Specification 1.0

## Status

Experimental engineering specification. PCWC is a transport-neutral contract for autonomous engineering work. It is not itself a cryptographic signature envelope.

## Purpose

PCWC binds one bounded work decision to observed pre-state, exact execution intent, protocol identity/version, agent/model provenance, trusted tools, governing invariants, simulation evidence, execution evidence, rollback semantics, and observed post-state.

## Authority rule

Transport is not authority. A protocol may carry a request. An agent may propose an action. A model may generate a candidate. A tool may produce evidence. None of those facts authorizes execution. CAIOS authorization remains deterministic and deny-by-default.

## Required fields

work_id — unique identifier for one bounded work item.
intent_fingerprint — SHA-256 digest of exact action intent.
action_kind — CAIOS allowlisted action class.
state_before — SHA-256 observation digest of pre-action repository state.
protocol / protocol_version — registered protocol identity and exact admitted revision.
agent_id — registry-backed proposal agent identifier, when external.
model_id / model_revision — exact model identity and artifact/service revision.
agent_attestation — digest binding proposal to agent/model provenance.
tool_ids — registry identifiers for every executable capability.
invariant_ids — registered protocol invariants governing the work.
simulation_digest — required for high-risk successful mutation.
execution_digest — digest of execution evidence.
state_after — required for successful work.

## High-risk rule

For risk at or above the configured high-risk threshold:
- at least two independent agent families must support the exact intent;
- at least two distinct model identities must support the exact intent;
- governing invariant identifiers must be present;
- simulation evidence is required before successful promotion;
- protected control surfaces remain unavailable to autonomous patches.

## Evidence rule

Every executed step must produce evidence. A successful certificate without corresponding execution evidence is invalid. A successful high-risk patch without simulation evidence is invalid.

## Provenance rule

Agent software provenance and model artifact provenance are independent. A valid agent wrapper does not imply a valid model artifact. A valid model artifact does not imply permission to use a hosted service. Service terms, model licenses, software licenses, and protocol permissions are separate admission dimensions.

## State rule

A PCWC may describe a proposed transition, but only the actual runtime can establish state_after. The minimum authoritative sequence is: observed state → simulation → deterministic verification → execution → post-state.

## Federation rule

Federated repositories are evidence sources. Cross-repository observations retain repository identity, current revision, dependency relation, verification status, and observation digest. Federation does not imply write authority.

## Release rule

PCWC records may be included in a release provenance package. Release artifacts may be signed with an external Sigstore-compatible attestation service. Routine test outputs should remain unsigned unless an explicit release policy requires signing.

## Failure semantics

Unknown protocol, agent, model, or tool; missing revisions; protocol mismatch; insufficient provenance; missing invariants; failed quorum; failed simulation; failed execution; missing post-state; proof mismatch; protected-surface patch; or unresolved canonical conformance causes rejection or HOLD.

## Non-goals

PCWC does not claim that any individual protocol or model is safe, that software licensing grants hosted-service rights, that an unsigned predicate is an attestation, that local mechanism presence establishes canonical conformance, or universal novelty.

The engineering claim is the specific synthesis of these controls into one autonomous work transaction.
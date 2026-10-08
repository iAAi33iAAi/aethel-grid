# CAIOS Autonomous Proof-Carrying Runtime

**Status:** experimental architecture / executable prototype  
**License:** Apache-2.0

## The problem this solves

Autonomous coding agents can already write code, run commands, and repair issues. What is missing is a deterministic constitutional control layer that can decide **whether the next autonomous action is admissible**, independently of model confidence.

Recent autonomous-software-engineering research reinforces the distinction between functional correctness and repository-policy compliance: SWE-CC reports that agents can produce functionally correct patches while still violating a substantial fraction of repository-specific policies. The architecture here treats policy/evidence compliance as a first-class gate instead of an afterthought.

## The new synthesis

CAIOS combines five normally separate concerns into one closed loop:

1. **Causal state** — AETHEL's event/history semantics.
2. **Constitutional gating** — Safety Kernel and ALGA-style fail-closed invariants.
3. **Model plurality** — any model or coding-agent backend can propose work.
4. **Proof-carrying execution** — every step emits an evidence certificate.
5. **Viability planning** — the controller chooses the next action using a deterministic score instead of model self-confidence.

### Control equation

```
NEXT = argmax_a
  [4P(a) + 3E(a) + 2R(a)] /
  [1 + 5K(a) + 2C(a)]
```

Where:

- **P** = expected progress
- **E** = evidence gained
- **R** = reversibility
- **K** = risk
- **C** = resource cost

The controller may only select actions that pass the constitutional gate.

## Proof-carrying autonomy

Every cycle emits a certificate containing:

- the observed repository state
- the current gap vector
- the chosen action
- deterministic action fingerprint
- machine-observed evidence
- reasons for continuation or halt
- elapsed time

This creates a causal chain:

```
observation → candidate set → gate → choice → execution → evidence → certificate → next observation
```

That chain is the core architectural novelty of this implementation.

## How models fit

The model layer is intentionally replaceable. The default adapter accepts an OpenAI-compatible HTTP endpoint, but the runtime can also be wrapped around external coding agents such as Aider, SWE-agent, or OpenHands without embedding their code.

This matters for IP and licensing: the CAIOS repository contains original orchestration code and integration contracts rather than copied agent implementations.

## Legal integration strategy

The first integration targets selected in the research pass were:

| Project | License | Intended role |
|---|---|---|
| Model Context Protocol | MIT | model/tool context boundary |
| Temporal Python SDK | MIT | durable execution option |
| Open Policy Agent | Apache-2.0 | policy evaluation option |
| in-toto | Apache-2.0 | execution/provenance evidence |
| Sigstore Cosign | Apache-2.0 | artifact signing |
| OpenTelemetry | Apache-2.0 | telemetry |
| NATS | Apache-2.0 | event transport |
| OpenSSF Scorecard | Apache-2.0 | repository security posture |
| Syft | Apache-2.0 | SBOM generation |
| Grype | Apache-2.0 | vulnerability scanning |
| Pydantic AI | MIT | structured model adapter option |
| Aider | Apache-2.0 | external coding-agent option |
| SWE-agent | MIT | external coding-agent option |
| OpenHands | MIT | external coding-agent option |

The runtime does not copy source from these projects. Where their tools are adopted, their licenses and notices must be retained and their actual version pinned.

AutoGPT requires special handling: the current repository is mixed-license; the `autogpt_platform/` portion is Polyform Shield while the classic/outside portions are MIT. The platform portion is therefore not a default dependency target for this design.

## What is not claimed

This document does **not** claim that no similar architecture exists anywhere. The defensible claim is that this repository introduces a specific synthesis: AETHEL causal state + constitutional gating + replaceable model proposals + proof-carrying execution + deterministic viability selection.

That distinction should remain explicit in investor and technical materials until independent prior-art research is completed.


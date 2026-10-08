# CAIOS Autonomous Proof-Carrying Runtime

**License: Apache-2.0**

CAIOS is a bounded autonomous control loop designed to sit above the existing AETHEL, Safety Kernel, and ALGA_FOLD_KERNEL components.

CAIOS is the supervisory control plane. In authority terms, CAIOS sits above the state substrate: it owns policy admission, candidate selection, and the decision to continue, halt, or require human review. AETHEL remains the deterministic constitutional/state substrate; Safety Kernel/ALGA remain execution-integrity boundaries.

The authority chain is:

**Human authority → CAIOS supervisory policy → AETHEL state/conformance → Safety/ALGA execution integrity → protocols/tools → agents/models → world effects**

This is an authority hierarchy, not a software dependency claim. The CAIOS process itself must still boot from trusted code and configured trust roots; it does not grant authority to itself merely by declaring it.

The key separation is:
**Model → proposes**  
**AETHEL → supplies deterministic state/history semantics**  
**ALGA/Safety → gate**  
**Executor → performs an allowlisted action**  
**Evidence → proves what happened**  
**Controller → selects the next action**

## Runtime law

No action is considered successful unless it returns machine-readable evidence.

No model response is treated as authority.

No autonomous patch is accepted outside the repository root or above the configured change budget.

## Run

```bash
python autonomy/caios_runtime.py --repo-root . --cycles 5
```

Certificates are written to:

```
ops/caios/autonomy-certificates.jsonl
```

The implementation is dependency-light and uses Python's standard library. External model and security tooling are adapter targets rather than vendored source.


## Federated mode

When `federation/system_manifest.json` is present, the runtime records a system-wide federation evidence object containing repository heads, presence, dependency pressure, and a deterministic system digest.

The dedicated GitHub Actions federation audit checks the public AETHEL-family repositories from a clean workspace. It is observation-only: discovering a problem never grants the controller permission to mutate another repository.

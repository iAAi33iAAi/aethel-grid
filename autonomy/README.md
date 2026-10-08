# CAIOS Autonomous Proof-Carrying Runtime

**License: Apache-2.0**

CAIOS is a bounded autonomous control loop designed to sit above the existing AETHEL, Safety Kernel, and ALGA_FOLD_KERNEL components.

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


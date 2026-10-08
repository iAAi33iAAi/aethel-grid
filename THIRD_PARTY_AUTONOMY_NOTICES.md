# Third-Party Autonomy Integration Notices

**Purpose:** machine-auditable record of external integration targets considered for CAIOS.

CAIOS integration is adapter-first: external source is not copied into the CAIOS core. A dependency is admitted only after version-specific license, provenance, security, and notice review.

## Current candidates

| Project | Current project-level license evidence | CAIOS role | Default treatment |
|---|---|---|---|
| Model Context Protocol specification / SDK | MIT | tool/context transport | adapter |
| OpenAI Agents Python | MIT | optional multi-agent proposal layer | adapter |
| Pydantic AI | MIT | typed model/tool adapter | adapter |
| Temporal Python SDK | MIT | durable execution/orchestration | adapter |
| Aider | Apache-2.0 | coding proposal backend | external process |
| SWE-agent | MIT | coding proposal backend | external process |
| OpenHands core | MIT; enterprise directory separately licensed | coding proposal backend | core only, exclude enterprise |
| Open Policy Agent | Apache-2.0 | policy evaluation | adapter |
| in-toto | Apache-2.0 | provenance/attestation | adapter |
| Sigstore Cosign | Apache-2.0 | artifact signing/verification | adapter |
| OpenTelemetry specification | Apache-2.0 | trace/evidence semantics | adapter |
| NATS server | Apache-2.0 | event transport | adapter |
| pyca/cryptography 50.0.2 | Apache-2.0 OR BSD-3-Clause | Ed25519 node identity | optional adapter; exact version pinned in CI |
| Wasmtime | Apache-2.0 | optional Wasm isolation boundary | adapter |
| Firecracker | Apache-2.0 | optional microVM isolation boundary | external service |
| OpenSSF Scorecard | Apache-2.0 | repository security evidence | external process |
| Syft | Apache-2.0 | SBOM generation | external process |
| Grype | Apache-2.0 | vulnerability evidence | external process |
| Dagster | Apache-2.0 | data/orchestration integration | optional adapter |
| Argo Workflows | Apache-2.0 | Kubernetes workflow execution | optional adapter |
| Argo Events | Apache-2.0 | event-driven automation | optional adapter |

## Code-model boundary

Model weights, checkpoints, hosted APIs, and training-data licenses are **not** treated as equivalent to source-code licenses. CAIOS therefore uses an OpenAI-compatible proposal interface and does not vendor model weights. Each chosen model must have a separate version-specific terms and provenance record before production use.

## Admission rule

1. Pin an exact version or commit.
2. Capture the exact license/NOTICE files.
3. Record SPDX identifier and provenance.
4. Generate an SBOM for distributed builds.
5. Run repository/security evidence before granting any execution capability.
6. Keep signing credentials outside model and proposal paths.
7. Never let an external model bypass the CAIOS constitutional gate.

This document is an engineering provenance record, not legal advice.

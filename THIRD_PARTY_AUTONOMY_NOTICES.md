# Third-Party Autonomy Integration Notices

**Purpose:** record integration targets researched for the CAIOS autonomous runtime.

The CAIOS code in this repository is original integration/orchestration code. No third-party source code is copied into these files.

## Permissive integration targets verified in the research pass

- Model Context Protocol specification — MIT
- Model Context Protocol Python SDK — MIT
- Temporal Python SDK — MIT
- Open Policy Agent — Apache-2.0
- in-toto — Apache-2.0
- Sigstore Cosign — Apache-2.0
- OpenTelemetry specification — Apache-2.0
- NATS server — Apache-2.0
- Dagster — Apache-2.0
- Prefect — Apache-2.0
- Argo Workflows — Apache-2.0
- Argo Events — Apache-2.0
- OpenSSF Scorecard — Apache-2.0
- Syft — Apache-2.0
- Grype — Apache-2.0
- Pydantic AI — MIT
- Aider — Apache-2.0
- SWE-agent — MIT
- OpenHands — MIT
- LlamaIndex — MIT
- Agent Zero — MIT

## Restricted / mixed-license target

AutoGPT is not treated as a blanket MIT dependency. Its current repository places `autogpt_platform/` under Polyform Shield and other portions under MIT. CAIOS therefore avoids depending on the Polyform Shield platform code by default.

## Compliance rule

For any future vendored code, copy the exact license and required notices from the exact version/commit being incorporated. Runtime dependencies should be pinned to a known version and tracked in a machine-readable software bill of materials.

This notice is an engineering record, not legal advice.

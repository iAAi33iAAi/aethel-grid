# CAIOS Bounded Autonomous Patch Loop

## Purpose

This workflow moves CAIOS from scheduled evidence collection toward a bounded software-development loop. It may propose and publish a **reviewable pull request** for a low-risk software patch. It does not merge or deploy changes, and it does not make constitutional decisions.

The design separates three trust zones.

1. **Proposal job:** trusted code on main sends a bounded context window to registered agents and writes one patch artifact. It has read-only repository permission and never executes the proposed code.
2. **Validation job:** downloads the patch in a separate job with read-only repository permission and no model API keys. It rechecks the base commit, agent/model admission, risk ceiling, protected paths, and deterministic gate, then applies the patch in a disposable standalone Git clone and runs the prescribed validation suite in a Bubblewrap namespace with network socket syscalls denied by seccomp, a hidden runner home, read-only system/toolchain mounts, a fresh process view, and only the isolated checkout and temporary workspace writable. If Bubblewrap, libseccomp, or the required syscall rules are unavailable, validation fails closed and the publisher job is skipped.
3. **Publisher job:** runs only after validation succeeds. It rechecks that main is still the validated base, applies the already-tested patch, commits it, and opens a pull request. It does **not** run candidate code and it never auto-merges.

The loop runs after pushes to main and on weekdays from the default branch. Merging the one-time agent configuration to main triggers its first configured run; the workflow can also be re-run from a previous main-branch Actions run.

## One-time activation requirements

The workflow intentionally does nothing until its agent configuration exists. This avoids inventing a model endpoint or sending code to a provider that has not been approved.

1. Create autonomy/agent_endpoints.json from autonomy/agent_endpoints.example.json, but do not enable egress until a separate reviewed record exists in autonomy/provider_endpoint_registry.json. The allowlist is intentionally empty by default. Each record pins the endpoint ID and exact URL, agent ID/version/source reference, protocol/version, model ID/revision, the allowed API-key secret name (or null for a no-key endpoint), and an approval reference. The configured JSON must match that record exactly; an unregistered URL is rejected before a source-context bundle is built. The record does not override agent/model/protocol admission. In particular, the OpenAI-compatible chat-completions wrapper is not the ACP/MCP agent protocol itself; see [Issue #14](https://github.com/iAAi33iAAi/aethel-grid/issues/14) before adding any provider entry. Do not use an endpoint record to bypass that adapter decision.
2. For at least one approved coding agent, explicitly set send_source_context to true. The context window has file-type, file-size, total-size and secret-name filters; the outbound egress policy blocks detected credential-like strings and rejects oversized contexts. This is still a deliberate source-code egress decision—review the provider and endpoint before enabling it.
3. Add the API key as a GitHub Actions repository secret matching the configured api_key_env. The workflow currently passes CAIOS_CODEX_API_KEY, CAIOS_GEMINI_API_KEY, CAIOS_ANTHROPIC_API_KEY, and CAIOS_OPENAI_API_KEY to the proposal step. Never put credentials in the JSON configuration.
4. Add CAIOS_AUTOBUILD_TOKEN as a fine-grained repository secret with only **Contents: read/write** and **Pull requests: read/write**. It is used only by the final push/PR step. A token is required because pull requests created using the default GITHUB_TOKEN do not ordinarily trigger other workflows; the token permits the normal CI checks to run on the generated pull request.

The connected GitHub integration cannot set repository secrets or add a reviewed endpoint entry without the endpoint, identity, terms, and credential choices above. The repository endpoint allowlist is empty in the current implementation, so no external provider can receive source context until that entry is reviewed and merged. Until configuration and secrets are supplied, the scheduled workflow reports NOT_CONFIGURED and makes no repository changes.

## Admission policy

- Only apply_patch proposals are eligible.
- Agent and model identity must pass repository-registry admission.
- The patch must be a valid unified diff and stay within the existing patch-size and line-count limits.
- The risk score must be below both the agent-registry high-risk threshold and the builder's fixed 0.45 ceiling.
- The non-removable protected-path baseline excludes the runtime, authority/tool policies, egress rules, sandbox and circuit breaker, evidence/promotion/provenance controls, and guardrail tests.
- The proposal job does not apply or execute the patch.
- The validation job independently revalidates the original proposal and tests it in a standalone clone using Bubblewrap/seccomp egress denial. It also removes the runner home, temporary credential paths, host process view, and Docker/runner sockets from the candidate namespace. No model API key or repository write token is present in the validation job. This is a constrained hosted-runner namespace—not a claim of a separately provisioned VM or a formally verified sandbox.
- The publishing job does not execute the patch. A stale base, missing token, failed check, malformed artifact, or denied proposal prevents publication.
- Pull requests remain subject to normal CI, review, and merge controls. The workflow never auto-merges and never deploys to physical infrastructure.

## Validation record

A successful workflow run records the base SHA, proposal digest, patch digest, agent attestation, gate result, fixed validation command, whether the network-none Docker container was used, and the sandbox test outcome. These records demonstrate what the workflow tested; they do not certify SPEC-004 as canonical or prove the policy itself is correct.

SPEC-004 remains blocked until its authoritative metric and canonical-byte semantics are supplied and independently conformed. The autonomous builder may improve ordinary application code, but it cannot invent the missing law or rewrite the controls that govern its own authority.

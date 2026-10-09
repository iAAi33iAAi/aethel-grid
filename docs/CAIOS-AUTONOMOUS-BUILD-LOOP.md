# CAIOS Bounded Autonomous Patch Loop

## Purpose

This workflow moves CAIOS from scheduled evidence collection toward a bounded software-development loop. It may propose and publish a **reviewable pull request** for a low-risk software patch. It does not merge or deploy changes, and it does not make constitutional decisions.

The design separates three trust zones.

1. **Proposal job:** trusted code on main sends a bounded context window to registered agents and writes one patch artifact. It has read-only repository permission and never executes the proposed code.
2. **Validation job:** downloads the patch in a separate job with read-only repository permission and no model API keys. It rechecks the base commit, agent/model admission, risk ceiling, protected paths, and deterministic gate, then applies the patch in a disposable Git worktree and runs the prescribed validation suite.
3. **Publisher job:** runs only after validation succeeds. It rechecks that main is still the validated base, applies the already-tested patch, commits it, and opens a pull request. It does **not** run candidate code and it never auto-merges.

The loop is scheduled on weekdays and can also be started manually through **Actions → CAIOS Bounded Autonomous Patch Loop → Run workflow**.

## One-time activation requirements

The workflow intentionally does nothing until its agent configuration exists. This avoids inventing a model endpoint or sending code to a provider that has not been approved.

1. Create autonomy/agent_endpoints.json from autonomy/agent_endpoints.example.json. Use an endpoint you are authorized to call, and match agent_id, model, exact revision, protocol, protocol version and provenance to the repository's agent/model registries.
2. For at least one approved coding agent, explicitly set send_source_context to true. The context window has file-type, file-size, total-size and secret-name filters; the outbound egress policy blocks detected credential-like strings and rejects oversized contexts. This is still a deliberate source-code egress decision—review the provider and endpoint before enabling it.
3. Add the API key as a GitHub Actions repository secret matching the configured api_key_env. The workflow currently passes CAIOS_CODEX_API_KEY, CAIOS_GEMINI_API_KEY, CAIOS_ANTHROPIC_API_KEY, and CAIOS_OPENAI_API_KEY to the proposal step. Never put credentials in the JSON configuration.
4. Add CAIOS_AUTOBUILD_TOKEN as a fine-grained repository secret with only **Contents: read/write** and **Pull requests: read/write**. It is used only by the final push/PR step. A token is required because pull requests created using the default GITHUB_TOKEN do not ordinarily trigger other workflows; the token permits the normal CI checks to run on the generated pull request.

The connected GitHub integration cannot set repository secrets or create autonomy/agent_endpoints.json without the endpoint, identity, and credential choices above. Until they are supplied, the scheduled workflow reports NOT_CONFIGURED and makes no repository changes.

## Admission policy

- Only apply_patch proposals are eligible.
- Agent and model identity must pass repository-registry admission.
- The patch must be a valid unified diff and stay within the existing patch-size and line-count limits.
- The risk score must be below both the agent-registry high-risk threshold and the builder's fixed 0.45 ceiling.
- The non-removable protected-path baseline excludes the runtime, authority/tool policies, egress rules, sandbox and circuit breaker, evidence/promotion/provenance controls, and guardrail tests.
- The proposal job does not apply or execute the patch.
- The validation job independently revalidates the original proposal and tests it in a disposable worktree. No model API key or repository write token is present in that job.
- The publishing job does not execute the patch. A stale base, missing token, failed check, malformed artifact, or denied proposal prevents publication.
- Pull requests remain subject to normal CI, review, and merge controls. The workflow never auto-merges and never deploys to physical infrastructure.

## Validation record

A successful workflow run records the base SHA, proposal digest, patch digest, agent attestation, gate result, fixed validation command, and sandbox test outcome. These records demonstrate what the workflow tested; they do not certify SPEC-004 as canonical or prove the policy itself is correct.

SPEC-004 remains blocked until its authoritative metric and canonical-byte semantics are supplied and independently conformed. The autonomous builder may improve ordinary application code, but it cannot invent the missing law or rewrite the controls that govern its own authority.

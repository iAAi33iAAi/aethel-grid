# AETHEL Agent Colony v0.1 — Toolboxes, Collaboration and Test Contract

## Purpose

This is the first safe execution shell for collaborative engineering work across the existing AETHEL/CAIOS repositories. It partitions work into narrow roles, gives each role a separate declared toolbox, and requires structured evidence before findings can be combined into a work queue.

**Scope note:** this version runs deterministic, read-only probes; it does not yet invoke independent foundation-model agents. The repository's provider-endpoint registry is empty, so model-backed collaboration is not configured by this change. No agent may write source, push, merge, access secret values, call an external model, change secrets, invoke live payments, or perform biometric actions.

## Agent lineup

| Agent | Toolbox | Responsibility | Output |
|---|---|---|---|
| Portfolio Cartographer | Repository/tree reader | Map repositories, commits, tests and dependencies | Inventory |
| Protocol Analyst | Specification/vector reader | Check canonical math, serialization and gate evidence | Protocol findings |
| Security Analyst | Auth/payment/privacy scanner | Detect sensitive file paths without printing contents; inspect safety boundaries | Security findings |
| DevOps/QA | CI/test-definition reader | Map workflows, tests, dependencies and verification scope | QA findings |
| Toolbox Architect | Policy/schema validator | Validate role-to-toolbox bindings and denial rules | Toolbox findings |
| Integration Synthesizer | Evidence joiner | Deduplicate and dependency-order findings | Work queue |
| Independent Red Team | Evidence challenger | Challenge missing evidence and unsafe tool permissions | Challenge report |
| Human Release Owner | Human-only gate | Approve, reject or require remediation | Approval record |

## Collaboration and execution

1. Inventory the portfolio and record available commit SHAs.
2. Run protocol, security, DevOps/QA and toolbox agents concurrently against the same checkout snapshot.
3. Run the evidence joiner and independent evidence-contract challenger concurrently.
4. Emit a JSON report with finding IDs, evidence paths, severity, recommendation and status.
5. Keep the final release decision on HOLD when critical/high risks or blocked canonical gates remain. Source changes must be a separate reviewed pull request.

## Toolbox contract

The deterministic workers call `ops/agent_colony/toolbox_policy.py` before using a declared capability. The dispatcher records ALLOW/DENY decisions, rejects missing/unknown agents, gives explicit denial rules precedence over allowlists, and fails closed when a requested capability is absent. This is an in-process policy boundary, not an operating-system sandbox; it is suitable only because this first worker set is trusted repository-owned code and never executes inspected repository code.

Toolbox capabilities are allowlists. Denials take precedence over an agent request. Automated agents must deny file writes, pushes, merges, secret reads and network requests. A proposed permission change is not effective until reviewed and tested. The human release owner is a gate, not an automatic source-code publisher.

## Reuse of the existing CAIOS agent stack

The colony does not invent a second model framework. Its architecture report inspects the existing `autonomy/agent_router.py` (capability ranking and independent-family quorum), `autonomy/multi_agent_provider.py` (parallel proposal calls), `autonomy/patch_proposal.py` (proposal-only patch planner), `autonomy/validate_patch_proposal.py` (secret-free network-none validator), and `.github/workflows/caios-autonomous-pr.yml` (proposal-to-PR pipeline). The current `autonomy/provider_endpoint_registry.json` has no endpoints and `autonomy/agent_endpoints.json` is absent, so real external model calls remain unconfigured. The colony now builds role-specific task packets in `ops/agent_colony/collaboration.py`, and `MultiAgentProposalProvider.propose(..., task_contexts=...)` passes a different bounded role packet to each registered endpoint while preserving the shared evidence snapshot. The automated test uses fake providers and a concurrency barrier to prove that protocol and security roles receive different toolboxes concurrently. These task packets are proposal context only—not callable tools or permission grants. Real endpoint configuration remains empty; the model-backed path is therefore tested through fakes, not activated against external models. Activation still requires operator-approved exact model/source/protocol pins, egress controls, secret-manager configuration and the existing isolated validator.

## Current deterministic probes

- Validate unique agent/toolbox IDs, dependency references, an acyclic graph and mandatory deny rules.
- Inventory repositories in the federation manifest, including checkout presence, current SHA, workflow/test path samples, declared verifier and its stated limits.
- Read the canonical protocol gate status.
- Detect non-example environment-file names without reading or emitting their contents.
- Check visible scanner-attestation and live Stripe-admission markers.
- Produce a JSON evidence report with conservative HOLD/REVIEW disposition.

## Limits

- A file-name detector cannot prove a secret is valid and can produce false positives.
- Text-marker checks are triage signals, not a full semantic security review.
- Passing these tests validates the colony tooling, not the AETHEL protocol, physical deployments or production safety.
- Model-backed collaboration requires a separately reviewed provider registry, authenticated endpoints, bounded egress, data classification, a network-isolated validator and a human-reviewed PR publisher. Never put API keys in the agent manifest or report.

## Run locally

    python -m unittest discover -s ops/agent_colony -p 'test_*.py' -v
    python ops/agent_colony/run_colony.py --repo-root . --manifest ops/agent_colony/manifest.json --system-manifest federation/system_manifest.json --output /tmp/aethel-agent-colony-report.json

The scanner does not execute source code from the inspected repositories. Portfolio test commands remain the responsibility of explicit CI jobs.

## Opt-in model-backed review — still disabled by default

The deterministic portfolio scanner remains offline and does not call a model. A separate adapter, `ops/agent_colony/model_review.py`, now preflights and can invoke the existing CAIOS proposal provider using the same four S1 role packets. It reuses `autonomy/patch_proposal.py` for registered endpoint, agent identity, model and protocol admission; it does not create a parallel provider runtime.

The adapter intentionally requires all four roles to have distinct registered provider identities: protocol, security, DevOps/QA and toolbox architecture. Every entry must match an exact `autonomy/provider_endpoint_registry.json` pin and carry an HTTPS approval reference in that registry. The runtime admission pass also checks the registered agent source and model/protocol allowlists before a call. Model-review entries must set `send_source_context: false`; only bounded finding metadata is included. Toolbox names are context labels, not callable tools.

No live configuration is committed. `ops/agent_colony/model_review_config.example.json` is a placeholder template, not an approved deployment configuration. Real activation requires the operator to register four distinct agent identities, exact endpoint URLs, exact model/revision and protocol/version pins, immutable source references and the appropriate approval references. API key values must remain outside the repository and may only be supplied through the named `CAIOS_*_API_KEY` environment variables or an approved secret manager.

### Commands

Run a no-network preflight first:

    python ops/agent_colony/model_review.py --repo-root .

When the approved configuration exists at `autonomy/agent_endpoints.json`, this command validates the pinned endpoint/role map without calling a model. If that file is absent, the result is `DISABLED`.

Only after endpoint reviews, model/license review, egress review and secret setup are complete, execution requires **both** the explicit flag `--execute-model-calls` and `CAIOS_ENABLE_MODEL_COLLABORATION=1`. Example for PowerShell, using a previously generated redacted evidence report:

    $env:CAIOS_ENABLE_MODEL_COLLABORATION = "1"
    python ops/agent_colony/model_review.py --repo-root . --config autonomy/agent_endpoints.json --evidence-report C:\path\to\aethel-agent-colony-report.json --execute-model-calls

The model call receives evidence metadata only. Returned content is treated as untrusted proposal text; command fields and diffs are discarded, nothing is applied, no tool is called, no branch/PR is created, and the final release decision remains `HOLD`. Review the output before considering any separate proposal workflow. Clear the environment switch after the approved test session:

    Remove-Item Env:CAIOS_ENABLE_MODEL_COLLABORATION

The automated test suite uses fake providers only. It never contacts external models and the workflow does not receive API credentials.

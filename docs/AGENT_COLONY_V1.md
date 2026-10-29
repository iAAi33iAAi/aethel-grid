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

Toolbox capabilities are allowlists. Denials take precedence over an agent request. Automated agents must deny file writes, pushes, merges, secret reads and network requests. A proposed permission change is not effective until reviewed and tested. The human release owner is a gate, not an automatic source-code publisher.

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

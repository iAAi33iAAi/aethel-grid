# CAIOS OpenAI-Compatible Proposal Transport

**Status:** Specified adapter contract, implementation present, external destination not approved.

## Purpose and identity

The `caios-openai-compatible-proposal-transport` protocol names the CAIOS HTTP adapter that sends a bounded request to a model inference endpoint and receives proposed actions. It is a **model-proposal transport**, not an interactive coding-agent protocol and not an authority to execute tools.

It must not be advertised as ACP, MCP, or A2A. Those protocols describe different agent/client, agent/tool, or agent-to-agent boundaries. A provider using an OpenAI-compatible chat-completions HTTP shape is not thereby an ACP/MCP coding agent.

The adapter's repository-owned identity is `caios-openai-compatible-proposal-adapter`, version `1.0.0`. Its source reference and SHA-256 are pinned in `autonomy/agent_registry.json`. The source reference must be immutable: either a full Git commit ID or a source URL containing a full commit ID (not a moving repository or branch URL). Changing the implementation requires a reviewed change that updates the version/source pin and SHA-256, then reruns the conformance/security checks. The runtime must fail closed if either the source reference is mutable or the local source digest does not match its registry record.

## Request contract

The adapter sends an HTTP POST to the exact URL pinned in `autonomy/provider_endpoint_registry.json`.

Request headers:

- `Content-Type: application/json`
- `Authorization: Bearer <secret>` only when an approved API-key environment variable is configured.

The request body contains:

- `model`: the exact model ID from the separately admitted model registry.
- `temperature: 0`.
- `messages`: a system instruction to return proposals only and a user message containing JSON-serialized snapshot data.

The model ID/revision and provider service terms are independent of the adapter's identity. The adapter version cannot be used to imply that a remote model or endpoint has been reviewed.

Endpoint rules:

- Absolute `https://` URLs are required for remote destinations.
- Plain `http://` is limited to local loopback addresses for development/testing.
- Embedded credentials, query strings, and fragments are rejected.
- HTTP redirects are rejected. The adapter does not follow a response to a second destination.
- The URL, adapter identity, agent version/source, protocol/version, model ID/revision, and approved API-key environment-variable name must match one exact reviewed endpoint registry record.
- Unknown or missing endpoint records are denied.

## Response contract

The adapter accepts either:

1. A JSON object with a top-level `proposals` array; or
2. A chat-completions response whose `choices[0].message.content` is a JSON string containing a `proposals` array.

Missing proposal data produces an empty proposal list. Invalid JSON or a transport error fails that worker; it does not grant another worker additional authority. Proposed data is still untrusted and must pass the normal schema checks, registry attestation, protected-surface gate, risk ceiling, independent revalidation, and sandbox validation.

## Source-context boundary

The adapter removes `source_context` unless the endpoint configuration explicitly sets `send_source_context: true`. When enabled, the existing egress policy scans the outbound payload and denies detected credential-like strings or other prohibited context. The sandboxed validation job never gets model API keys or a repository write token.

Source-code egress is a separate, explicit approval decision. Registering the adapter or protocol does not approve a provider URL, accept service terms, admit a model ID/revision, or enable source-context sharing.

## Tool-execution boundary

This adapter has `external_tool_execution: false`. It only returns proposals through the model response. It does not launch a CLI agent, execute a tool, run shell commands, write patches, merge pull requests, or deploy to infrastructure. The trusted CAIOS pipeline handles proposal identity, checks, and publication separately; proposals do not execute automatically.

To run an actual Codex/Gemini/Claude/OpenHands coding agent through ACP, MCP, or another protocol, implement and register a distinct process/agent adapter that invokes that real protocol. Do not relabel this HTTP client as that coding agent.

## Current activation state

`autonomy/provider_endpoint_registry.json` intentionally contains an empty `endpoints` array. `autonomy/agent_endpoints.example.json` is a template only and does not identify an approved remote provider or admitted model. Until a reviewed exact endpoint binding and valid model/terms record exist, the proposal workflow must remain inert and send no source context externally.

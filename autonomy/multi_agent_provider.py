#!/usr/bin/env python3
"""
CAIOS multi-agent proposal transport.

Each configured endpoint is a proposal worker. The provider normalizes its
output with a registry identity before the runtime's deterministic attestation
and gate. Failures in one worker do not grant authority to another.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True)
class EndpointSpec:
    agent_id: str
    endpoint: str
    model: str
    protocol: str
    agent_version: str
    source_ref: str
    model_revision: str = ""
    protocol_version: str = "1"
    api_key: str | None = None
    max_proposals: int = 8
    send_source_context: bool = False


class MultiAgentProposalProvider:
    def __init__(
        self,
        specs: tuple[EndpointSpec, ...],
        provider_factory: Callable[..., Any] | None = None,
        max_workers: int = 8,
    ) -> None:
        self.specs = specs
        self.provider_factory = provider_factory
        self.max_workers = max_workers
        self.last_errors: list[dict[str, str]] = []

    def _call(self, spec: EndpointSpec, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        factory = self.provider_factory
        if factory is None:
            from autonomy.caios_runtime import OpenAICompatibleProposalProvider
            factory = OpenAICompatibleProposalProvider
        try:
            provider = factory(
                endpoint=spec.endpoint,
                model=spec.model,
                api_key=spec.api_key,
                send_source_context=spec.send_source_context,
            )
        except TypeError:
            provider = factory(
                endpoint=spec.endpoint,
                model=spec.model,
                api_key=spec.api_key,
            )
        rows = provider.propose(snapshot)
        normalized = []
        for row in rows[: spec.max_proposals]:
            if not isinstance(row, dict):
                continue
            proposal = dict(row)
            proposal.update(
                {
                    "agent_id": spec.agent_id,
                    "protocol": spec.protocol,
                    "protocol_version": spec.protocol_version,
                    "model_id": spec.model,
                    "model_revision": spec.model_revision,
                    "agent_version": spec.agent_version,
                    "source_ref": spec.source_ref,
                }
            )
            normalized.append(proposal)
        return normalized

    def propose(
        self,
        snapshot: dict[str, Any],
        *,
        task_contexts: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Fan out one shared evidence snapshot plus an optional role-specific task per endpoint.

        The task context is passed as data only. It grants no tool authority, does not
        execute returned commands, and is still subject to egress policy, proposal
        attestation, deterministic gates and isolated validation.
        """
        if not isinstance(snapshot, dict):
            raise TypeError("snapshot must be a dictionary")
        task_contexts = task_contexts or {}
        if not isinstance(task_contexts, dict) or any(
            not isinstance(agent_id, str) or not isinstance(task, dict)
            for agent_id, task in task_contexts.items()
        ):
            raise ValueError("task_contexts must map agent IDs to dictionaries")
        configured_ids = {spec.agent_id for spec in self.specs}
        unknown_ids = set(task_contexts) - configured_ids
        if unknown_ids:
            raise ValueError("task context supplied for unconfigured agent IDs: " + ",".join(sorted(unknown_ids)))
        proposals = []
        self.last_errors = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(self.specs)))) as pool:
            futures = {}
            for spec in self.specs:
                worker_snapshot = dict(snapshot)
                if spec.agent_id in task_contexts:
                    worker_snapshot["agent_task"] = dict(task_contexts[spec.agent_id])
                futures[pool.submit(self._call, spec, worker_snapshot)] = spec
            for future in as_completed(futures):
                spec = futures[future]
                try:
                    proposals.extend(future.result())
                except Exception as exc:
                    self.last_errors.append(
                        {
                            "agent_id": spec.agent_id,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
        return sorted(
            proposals,
            key=lambda item: (
                str(item.get("agent_id", "")),
                str(item.get("action_id", "")),
                str(item.get("kind", "")),
            ),
        )

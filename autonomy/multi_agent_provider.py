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
    api_key: str | None = None
    max_proposals: int = 8


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

    def _call(self, spec: EndpointSpec, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        factory = self.provider_factory
        if factory is None:
            from autonomy.caios_runtime import OpenAICompatibleProposalProvider
            factory = OpenAICompatibleProposalProvider
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
                    "model_id": spec.model,
                    "agent_version": spec.agent_version,
                    "source_ref": spec.source_ref,
                }
            )
            normalized.append(proposal)
        return normalized

    def propose(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        proposals = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(self.specs)))) as pool:
            futures = {pool.submit(self._call, spec, snapshot): spec for spec in self.specs}
            for future in as_completed(futures):
                spec = futures[future]
                try:
                    proposals.extend(future.result())
                except Exception:
                    # A worker failure is evidence for the caller's logging
                    # layer; it never becomes an implicit approval.
                    continue
        return proposals

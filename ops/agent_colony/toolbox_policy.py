"""Fail-closed in-process capability gate for the deterministic colony workers.

This is an application policy boundary, not an OS sandbox. It is safe here only
because worker code is trusted, fixed repository-owned code; inspected repo
code is never imported or executed by the colony.
"""
from __future__ import annotations
from threading import Lock
from typing import Any


class ToolboxPermissionError(PermissionError):
    """Raised when a worker asks for a capability not granted by its toolbox."""


class ToolboxDispatcher:
    def __init__(self, manifest: dict[str, Any]) -> None:
        self.agents = {item["id"]: item for item in manifest.get("agents", [])}
        self.toolboxes = {item["id"]: item for item in manifest.get("toolboxes", [])}
        self._events: list[dict[str, str]] = []
        self._lock = Lock()

    def authorize(self, agent_id: str, capability: str, resource: str = "") -> None:
        agent = self.agents.get(agent_id)
        box = self.toolboxes.get(agent.get("toolbox_id")) if agent else None
        if not agent or not box:
            decision, reason, toolbox_id = "DENY", "unknown agent or toolbox", "unavailable"
        elif capability in set(box.get("deny", [])):
            decision, reason, toolbox_id = "DENY", "capability explicitly denied", box["id"]
        elif capability not in set(box.get("allow", [])):
            decision, reason, toolbox_id = "DENY", "capability not on allowlist", box["id"]
        else:
            decision, reason, toolbox_id = "ALLOW", "allowlisted", box["id"]
        event = {"agent_id": agent_id, "toolbox_id": toolbox_id, "capability": capability,
                 "decision": decision, "reason": reason, "resource": resource}
        with self._lock:
            self._events.append(event)
        if decision != "ALLOW":
            raise ToolboxPermissionError(f"{agent_id} denied capability {capability}: {reason}")

    def audit_log(self) -> list[dict[str, str]]:
        with self._lock:
            return [dict(item) for item in self._events]

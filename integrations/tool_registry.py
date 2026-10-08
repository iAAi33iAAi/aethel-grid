#!/usr/bin/env python3
"""
CAIOS explicit tool registry.

Only tools named in the repository-owned registry may be selected by future
adapters. The registry describes capability and provenance; it does not grant
permission to execute an arbitrary command.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    capability: str
    authority: str
    license: str
    command: tuple[str, ...] = ()
    scope_note: str = ""

    @property
    def executable(self) -> str | None:
        if not self.command:
            return None
        return shutil.which(self.command[0])


class ToolRegistry:
    def __init__(self, repo_root: Path, path: str = "integrations/caios_tool_registry.json") -> None:
        self.repo_root = repo_root.resolve()
        raw = json.loads((self.repo_root / path).read_text(encoding="utf-8"))
        self.policy = dict(raw.get("policy", {}))
        self.tools = {
            str(item["id"]): ToolSpec(
                tool_id=str(item["id"]),
                capability=str(item["capability"]),
                authority=str(item["authority"]),
                license=str(item["license"]),
                command=tuple(str(part) for part in item.get("command", [])),
                scope_note=str(item.get("scope_note", "")),
            )
            for item in raw.get("tools", [])
        }

    def get(self, tool_id: str) -> ToolSpec | None:
        return self.tools.get(tool_id)

    def available(self) -> list[dict[str, object]]:
        result = []
        for spec in self.tools.values():
            result.append({
                "id": spec.tool_id,
                "capability": spec.capability,
                "authority": spec.authority,
                "license": spec.license,
                "available": bool(spec.executable) if spec.command else None,
                "scope_note": spec.scope_note,
            })
        return sorted(result, key=lambda item: str(item["id"]))

    def admits(self, tool_id: str) -> bool:
        return tool_id in self.tools

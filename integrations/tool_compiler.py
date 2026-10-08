#!/usr/bin/env python3
"""
CAIOS registry-backed tool command compiler.

No model output is accepted as argv. The caller supplies only bounded,
deterministic arguments for a tool that already exists in the trusted registry.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from integrations.tool_registry import ToolRegistry


@dataclass(frozen=True)
class CompiledCommand:
    tool_id: str
    argv: tuple[str, ...]
    executable_path: str
    authority: str
    command_digest: str


def compile_command(
    repo_root: Path,
    tool_id: str,
    args: tuple[str, ...] = (),
) -> tuple[CompiledCommand | None, str]:
    registry = ToolRegistry(repo_root)
    spec = registry.get(tool_id)
    if spec is None:
        return None, "tool-not-registered"
    if not spec.command:
        return None, "tool-command-not-declared"

    executable = shutil.which(spec.command[0])
    if not executable:
        return None, "tool-executable-unavailable"

    normalized_args = tuple(str(item) for item in args)
    if spec.argument_policy == "none" and normalized_args:
        return None, "tool-arguments-not-permitted"
    if spec.argument_policy == "path-only":
        for item in normalized_args:
            if item.startswith("-"):
                return None, "tool-flag-not-permitted"
            candidate = (repo_root / item).resolve()
            try:
                candidate.relative_to(repo_root.resolve())
            except ValueError:
                return None, "tool-argument-escapes-repository"
    elif spec.argument_policy != "none":
        return None, "unknown-tool-argument-policy"

    argv = tuple(spec.command) + normalized_args
    if any("\x00" in part for part in argv):
        return None, "command-contains-null-byte"

    from autonomy.evidence_bundle import digest

    return (
        CompiledCommand(
            tool_id=tool_id,
            argv=argv,
            executable_path=executable,
            authority=spec.authority,
            command_digest=digest({
                "tool_id": tool_id,
                "argv": list(argv),
                "authority": spec.authority,
            }),
        ),
        "compiled",
    )

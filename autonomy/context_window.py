#!/usr/bin/env python3
"""
CAIOS bounded model context window.

Source context is opt-in. Files are allowlisted by path/extension, size, and
content class. Secret-looking files and generated artifacts are excluded.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


DEFAULT_EXTENSIONS = frozenset({
    ".py", ".pyi", ".rs", ".toml", ".json", ".yaml", ".yml", ".md", ".txt",
    ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".kt", ".swift", ".sql",
    ".sh", ".bash", ".c", ".cc", ".cpp", ".h", ".hpp",
})

SECRET_NAMES = (
    ".env",
    "credentials",
    "secret",
    "token",
    "private_key",
    "id_rsa",
    "service-account",
)

GENERATED_PARTS = (
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "vendor",
)


def is_secret_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in SECRET_NAMES)


def is_generated_path(path: str) -> bool:
    return any(part in GENERATED_PARTS for part in Path(path).parts)


class ContextWindow:
    def __init__(
        self,
        repo_root: Path,
        *,
        max_files: int = 24,
        max_file_bytes: int = 12000,
        max_total_bytes: int = 120000,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes

    def build(self) -> dict[str, object]:
        files = []
        total = 0

        try:
            paths = sorted(
                p for p in self.repo_root.rglob("*")
                if not p.is_symlink() and p.is_file() and ".git" not in p.parts
            )
        except OSError:
            paths = []

        for path in paths:
            relative = path.relative_to(self.repo_root).as_posix()
            if is_secret_path(relative) or is_generated_path(relative):
                continue
            if path.suffix.lower() not in DEFAULT_EXTENSIONS:
                continue
            if path.stat().st_size > self.max_file_bytes:
                continue
            if len(files) >= self.max_files or total + path.stat().st_size > self.max_total_bytes:
                break
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            files.append({
                "path": relative,
                "content": text,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            })
            total += path.stat().st_size

        material = {
            "schema": "caios-source-context/v1",
            "files": files,
            "file_count": len(files),
            "total_bytes": total,
        }
        material["context_digest"] = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return material

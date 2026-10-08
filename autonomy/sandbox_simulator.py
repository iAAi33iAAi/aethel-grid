#!/usr/bin/env python3
"""
CAIOS disposable worktree simulator.

A proposed patch is tested against a detached git worktree before the real
working tree is mutated. The simulator accepts only a trusted validation
command; it never executes a model-supplied shell string.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SimulationResult:
    status: str
    patch_check_returncode: int
    validation_returncode: int | None
    stdout_tail: str
    stderr_tail: str
    worktree: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "patch_check_returncode": self.patch_check_returncode,
            "validation_returncode": self.validation_returncode,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "worktree": self.worktree,
        }


class DisposableWorktree:
    def __init__(self, repo_root: Path, timeout_seconds: int = 180) -> None:
        self.repo_root = repo_root.resolve()
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        patch_text: str,
        validation_command: tuple[str, ...],
    ) -> SimulationResult:
        worktree = Path(tempfile.mkdtemp(prefix="caios-sim-"))

        def exec_cmd(args: tuple[str, ...]) -> tuple[int, str, str]:
            proc = subprocess.run(
                args,
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            return proc.returncode, proc.stdout, proc.stderr

        try:
            subprocess.run(
                ("git", "-C", str(self.repo_root), "worktree", "add", "--detach", str(worktree), "HEAD"),
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            patch_path = worktree / ".caios-sim.patch"
            patch_path.write_text(patch_text, encoding="utf-8")

            check_rc, _, check_err = exec_cmd(("git", "apply", "--check", str(patch_path)))
            if check_rc != 0:
                return SimulationResult(
                    status="FAIL",
                    patch_check_returncode=check_rc,
                    validation_returncode=None,
                    stdout_tail="",
                    stderr_tail=check_err[-4000:],
                    worktree=str(worktree),
                )

            apply_rc, _, apply_err = exec_cmd(("git", "apply", str(patch_path)))
            if apply_rc != 0:
                return SimulationResult(
                    status="FAIL",
                    patch_check_returncode=check_rc,
                    validation_returncode=apply_rc,
                    stdout_tail="",
                    stderr_tail=apply_err[-4000:],
                    worktree=str(worktree),
                )

            rc, stdout, stderr = exec_cmd(validation_command)
            return SimulationResult(
                status="PASS" if rc == 0 else "FAIL",
                patch_check_returncode=check_rc,
                validation_returncode=rc,
                stdout_tail=stdout[-4000:],
                stderr_tail=stderr[-4000:],
                worktree=str(worktree),
            )
        except subprocess.TimeoutExpired as exc:
            return SimulationResult(
                status="FAIL",
                patch_check_returncode=1,
                validation_returncode=None,
                stdout_tail=str(getattr(exc, "stdout", "") or "")[-4000:],
                stderr_tail=str(getattr(exc, "stderr", "") or "")[-4000:],
                worktree=str(worktree),
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            return SimulationResult(
                status="FAIL",
                patch_check_returncode=1,
                validation_returncode=None,
                stdout_tail="",
                stderr_tail=str(exc)[-4000:],
                worktree=str(worktree),
            )
        finally:
            subprocess.run(
                ("git", "-C", str(self.repo_root), "worktree", "remove", "--force", str(worktree)),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            shutil.rmtree(worktree, ignore_errors=True)

#!/usr/bin/env python3
"""
CAIOS disposable worktree simulator.

A proposed patch is tested against a disposable standalone Git clone before the
real working tree is mutated. Strict validation can run it in a disposable
Docker container with networking disabled, all Linux capabilities dropped,
a read-only container root, and only the candidate clone mounted writable.
The simulator accepts only a trusted validation command; it never executes a
model-supplied shell string.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import os
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
    egress_blocked: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "patch_check_returncode": self.patch_check_returncode,
            "validation_returncode": self.validation_returncode,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "worktree": self.worktree,
            "egress_blocked": self.egress_blocked,
        }


class DisposableWorktree:
    def __init__(self, repo_root: Path, timeout_seconds: int = 180) -> None:
        self.repo_root = repo_root.resolve()
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        patch_text: str,
        validation_command: tuple[str, ...],
        *,
        require_egress_block: bool = False,
    ) -> SimulationResult:
        # Keep the candidate clone in a dedicated host temp path. Strict validation
        # mounts only this clone into Docker; other host directories are not mounted.
        worktree = Path(tempfile.mkdtemp(prefix="caios-sim-", dir="/var/tmp"))
        sandbox_tmp = Path(tempfile.mkdtemp(prefix="caios-tmp-"))
        sandbox_home = Path(tempfile.mkdtemp(prefix="caios-home-", dir=str(sandbox_tmp)))
        # The parent process and ordinary local patch checks only receive a
        # minimal environment. Strict validation runs inside a Docker container
        # with no network, no capabilities, a read-only root, and one writable
        # mount for the disposable candidate clone.
        sandbox_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(sandbox_home),
            "TMPDIR": str(sandbox_tmp),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "CI": "true",
            "PYTHONUNBUFFERED": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        }

        def exec_cmd(
            args: tuple[str, ...],
            *,
            block_egress: bool = False,
        ) -> tuple[int, str, str]:
            if block_egress:
                docker = shutil.which("docker")
                if not docker:
                    return 127, "", "egress-block-unavailable:docker-not-installed"
                image = os.environ.get(
                    "CAIOS_SANDBOX_IMAGE",
                    "caios-validation-sandbox:ci",
                )
                image_check = subprocess.run(
                    (docker, "image", "inspect", image),
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                if image_check.returncode != 0:
                    return 127, "", "egress-block-unavailable:sandbox-image-not-built"
                command = [
                    docker, "run", "--rm",
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--pids-limit=256",
                    "--memory=6g",
                    "--cpus=2",
                    "--tmpfs", "/tmp:rw,nosuid,nodev,size=1g",
                    "--tmpfs", "/run:rw,nosuid,nodev,size=64m",
                    "--mount", f"type=bind,src={worktree},dst=/workspace,rw",
                    "--workdir", "/workspace",
                    "--user", f"{os.getuid()}:{os.getgid()}",
                    "--env", "HOME=/tmp",
                    "--env", "TMPDIR=/tmp",
                    "--env", "PATH=/opt/venv/bin:/usr/local/cargo/bin:/usr/local/bin:/usr/bin:/bin",
                    "--env", "LANG=C.UTF-8",
                    "--env", "LC_ALL=C.UTF-8",
                    "--env", "CI=true",
                    "--env", "PYTHONUNBUFFERED=1",
                    "--env", "PYTHONNOUSERSITE=1",
                    "--env", "PYTHONDONTWRITEBYTECODE=1",
                    "--env", "GIT_CONFIG_NOSYSTEM=1",
                    "--env", "GIT_CONFIG_GLOBAL=/dev/null",
                    "--env", "CAIOS_EGRESS_BLOCKED=true",
                    image,
                    *args,
                ]
                proc = subprocess.run(
                    tuple(command),
                    cwd=Path("/"),
                    env=sandbox_env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            else:
                proc = subprocess.run(
                    args,
                    cwd=worktree,
                    env=sandbox_env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            return proc.returncode, proc.stdout, proc.stderr

        try:
            subprocess.run(
                ("git", "clone", "--no-hardlinks", "--quiet", str(self.repo_root), str(worktree)),
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            patch_path = sandbox_tmp / ".caios-sim.patch"
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

            rc, stdout, stderr = exec_cmd(
                validation_command,
                block_egress=require_egress_block,
            )
            return SimulationResult(
                status="PASS" if rc == 0 else "FAIL",
                patch_check_returncode=check_rc,
                validation_returncode=rc,
                stdout_tail=stdout[-4000:],
                stderr_tail=stderr[-4000:],
                worktree=str(worktree),
                egress_blocked=bool(require_egress_block and rc == 0),
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
            shutil.rmtree(worktree, ignore_errors=True)
            shutil.rmtree(sandbox_tmp, ignore_errors=True)

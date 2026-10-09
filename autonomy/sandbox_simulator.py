#!/usr/bin/env python3
"""
CAIOS disposable worktree simulator.

A proposed patch is tested against a disposable standalone Git clone before the
real working tree is mutated. Untrusted candidate validation can require a
Bubblewrap namespace with no network. The simulator accepts only a trusted
validation command; it never executes a model-supplied shell string.

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
    network_isolated: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "patch_check_returncode": self.patch_check_returncode,
            "validation_returncode": self.validation_returncode,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "worktree": self.worktree,
            "network_isolated": self.network_isolated,
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
        require_network_isolation: bool = False,
    ) -> SimulationResult:
        # Keep the candidate checkout outside HOME and TMPDIR so those locations
        # can be hidden/replaced inside Bubblewrap without hiding the checkout.
        worktree = Path(tempfile.mkdtemp(prefix="caios-sim-", dir="/var/tmp"))
        sandbox_tmp = Path(tempfile.mkdtemp(prefix="caios-tmp-"))
        sandbox_home = Path(tempfile.mkdtemp(prefix="caios-home-", dir=str(sandbox_tmp)))
        toolchain_mounts: dict[str, tuple[str, str]] = {}

        # Candidate/test code must not inherit ambient secrets, provider keys,
        # GitHub tokens, cloud credentials, proxies, or custom Python paths.
        # Preserve only tool lookup and the pinned Rust toolchain locations.
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
        host_home = Path.home().resolve()
        for var_name, default_path, shadow_name in (
            ("CARGO_HOME", host_home / ".cargo", "caios-cargo"),
            ("RUSTUP_HOME", host_home / ".rustup", "caios-rustup"),
        ):
            original = Path(os.environ.get(var_name, str(default_path))).resolve()
            if not original.is_dir() or not original.is_relative_to(host_home):
                continue
            shadow_path = sandbox_tmp / shadow_name
            shadow_path.mkdir()
            if var_name == "CARGO_HOME":
                # Only expose executable shims. The broader Cargo home may
                # include registry credentials/configuration and is not mounted.
                source = original / "bin"
                target = shadow_path / "bin"
                target.mkdir()
                if source.is_dir():
                    toolchain_mounts[var_name] = (str(source), str(target))
                    sandbox_env[var_name] = f"/tmp/{shadow_name}"
                    sandbox_env["PATH"] = sandbox_env["PATH"].replace(
                        str(source), f"/tmp/{shadow_name}/bin"
                    )
            else:
                toolchain_mounts[var_name] = (str(original), str(shadow_path))
                sandbox_env[var_name] = f"/tmp/{shadow_name}"

        def exec_cmd(
            args: tuple[str, ...],
            *,
            isolate_network: bool = False,
        ) -> tuple[int, str, str]:
            command = args
            if isolate_network:
                bwrap = shutil.which("bwrap")
                if not bwrap:
                    return 127, "", "network-isolation-unavailable:bwrap-not-installed"
                host_home_str = str(host_home)
                command_list = [
                    bwrap,
                    "--die-with-parent",
                    "--unshare-net",
                    "--unshare-pid",
                    "--unshare-ipc",
                    "--unshare-uts",
                    "--ro-bind", "/", "/",
                    "--bind", str(sandbox_tmp), "/tmp",
                    "--proc", "/proc",
                    "--dev", "/dev",
                ]
                # Expose only the Rust executable shims and rustup toolchains
                # read-only. Cargo credential/config directories are never mounted.
                for var_name, (source, target) in toolchain_mounts.items():
                    command_list.extend(["--ro-bind", source, f"/tmp/{Path(target).relative_to(sandbox_tmp).as_posix()}"])
                if host_home_str not in {"/", "/tmp", "/var/tmp"}:
                    command_list.extend(["--tmpfs", host_home_str])
                command_list.extend(["--tmpfs", "/run", "--tmpfs", "/var/tmp"])
                command_list.extend(["--chdir", "/tmp/workspace"])
                for key, value in sandbox_env.items():
                    sandbox_value = value
                    if key == "HOME":
                        sandbox_value = f"/tmp/{sandbox_home.name}"
                    elif key == "TMPDIR":
                        sandbox_value = "/tmp"
                    command_list.extend(["--setenv", key, sandbox_value])
                command_list.extend(args)
                command = tuple(command_list)
            proc = subprocess.run(
                command,
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

            if require_network_isolation:
                isolated_workspace = sandbox_tmp / "workspace"
                shutil.copytree(worktree, isolated_workspace, symlinks=True)
            rc, stdout, stderr = exec_cmd(
                validation_command,
                isolate_network=require_network_isolation,
            )
            return SimulationResult(
                status="PASS" if rc == 0 else "FAIL",
                patch_check_returncode=check_rc,
                validation_returncode=rc,
                stdout_tail=stdout[-4000:],
                stderr_tail=stderr[-4000:],
                worktree=str(worktree),
                network_isolated=bool(require_network_isolation and rc == 0),
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

#!/usr/bin/env python3
"""
CAIOS disposable worktree simulator.

A proposed patch is tested against a disposable standalone Git clone before the
real working tree is mutated. Untrusted candidate validation can require Bubblewrap filesystem isolation and
seccomp-denied network socket operations. The simulator accepts only a trusted
validation command; it never executes a model-supplied shell string.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import ctypes
import errno
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class _SeccompArgCmp(ctypes.Structure):
    _fields_ = [
        ("arg", ctypes.c_uint),
        ("op", ctypes.c_int),
        ("datum_a", ctypes.c_uint64),
        ("datum_b", ctypes.c_uint64),
    ]


def _export_egress_block_filter(fd: int) -> None:
    """Compile a libseccomp filter that denies network socket operations."""
    try:
        lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    except OSError as exc:
        raise RuntimeError("libseccomp-unavailable") from exc

    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint
    ]
    lib.seccomp_rule_add.restype = ctypes.c_int
    lib.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
        ctypes.c_uint, ctypes.POINTER(_SeccompArgCmp),
    ]
    lib.seccomp_rule_add_array.restype = ctypes.c_int
    lib.seccomp_export_bpf.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.seccomp_export_bpf.restype = ctypes.c_int
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.restype = None

    # SCMP_ACT_ALLOW = 0x7fff0000; SCMP_ACT_ERRNO(EPERM) = 0x00050000 | EPERM.
    ctx = lib.seccomp_init(0x7FFF0000)
    if not ctx:
        raise RuntimeError("seccomp-init-failed")
    deny = 0x00050000 | errno.EPERM

    def resolve(name: str, required: bool = True) -> int:
        number = lib.seccomp_syscall_resolve_name(name.encode("ascii"))
        if number < 0 and required:
            raise RuntimeError(f"seccomp-syscall-not-resolved:{name}")
        return number

    try:
        # Allow socket/socketpair only for AF_UNIX. AF_INET, AF_INET6,
        # netlink, packet, vsock, and all other address families are denied.
        not_unix = _SeccompArgCmp(0, 1, 1, 0)  # SCMP_CMP_NE, AF_UNIX == 1
        for syscall_name in ("socket", "socketpair"):
            number = resolve(syscall_name)
            result = lib.seccomp_rule_add_array(
                ctx, deny, number, 1, ctypes.byref(not_unix)
            )
            if result < 0:
                raise RuntimeError(
                    f"seccomp-socket-domain-rule-failed:{syscall_name}:{result}"
                )

        # Deny connection, listener, and data-transfer paths, including
        # message batching and io_uring-based indirect socket operations.
        required = {
            "connect", "bind", "listen", "accept",
            "sendto", "recvfrom", "sendmsg", "recvmsg", "shutdown",
        }
        blocked_syscalls = (
            "connect", "bind", "listen", "accept", "accept4", "socketcall",
            "sendto", "recvfrom", "sendmsg", "recvmsg", "sendmmsg",
            "recvmmsg", "shutdown", "io_uring_setup", "io_uring_enter",
            "io_uring_register", "bpf", "ptrace",
        )
        for syscall_name in blocked_syscalls:
            number = resolve(syscall_name, required=syscall_name in required)
            if number < 0:
                continue
            result = lib.seccomp_rule_add(ctx, deny, number, 0)
            if result < 0:
                raise RuntimeError(
                    f"seccomp-syscall-rule-failed:{syscall_name}:{result}"
                )

        result = lib.seccomp_export_bpf(ctx, fd)
        if result < 0:
            raise RuntimeError(f"seccomp-bpf-export-failed:{result}")
    finally:
        lib.seccomp_release(ctx)


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
        isolated_env = dict(sandbox_env)
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
                    sandbox_env[var_name] = str(original)
                    isolated_env[var_name] = f"/tmp/{shadow_name}"
                    isolated_env["PATH"] = isolated_env["PATH"].replace(
                        str(source), f"/tmp/{shadow_name}/bin"
                    )
            else:
                toolchain_mounts[var_name] = (str(original), str(shadow_path))
                sandbox_env[var_name] = str(original)
                isolated_env[var_name] = f"/tmp/{shadow_name}"

        def exec_cmd(
            args: tuple[str, ...],
            *,
            block_egress: bool = False,
        ) -> tuple[int, str, str]:
            command = args
            seccomp_file = None
            pass_fds: tuple[int, ...] = ()
            if block_egress:
                bwrap = shutil.which("bwrap")
                if not bwrap:
                    return 127, "", "egress-block-unavailable:bwrap-not-installed"
                try:
                    seccomp_file = tempfile.TemporaryFile()
                    _export_egress_block_filter(seccomp_file.fileno())
                    seccomp_file.flush()
                    seccomp_file.seek(0)
                except Exception as exc:
                    if seccomp_file is not None:
                        seccomp_file.close()
                    return 127, "", f"egress-block-unavailable:{type(exc).__name__}:{exc}"
                pass_fds = (seccomp_file.fileno(),)
                host_home_str = str(host_home)
                command_list = [
                    bwrap,
                    "--die-with-parent",
                    "--unshare-pid",
                    "--unshare-ipc",
                    "--unshare-uts",
                    "--ro-bind", "/", "/",
                    "--bind", str(sandbox_tmp), "/tmp",
                    "--proc", "/proc",
                    "--dev", "/dev",
                    "--seccomp", str(seccomp_file.fileno()),
                ]
                # Expose only Rust executable shims and rustup toolchain files
                # read-only. Cargo credential/config directories are not mounted.
                for var_name, (source, target) in toolchain_mounts.items():
                    command_list.extend(["--ro-bind", source, f"/tmp/{Path(target).relative_to(sandbox_tmp).as_posix()}"])
                if host_home_str not in {"/", "/tmp", "/var/tmp"}:
                    command_list.extend(["--tmpfs", host_home_str])
                command_list.extend(["--tmpfs", "/run", "--tmpfs", "/var/tmp"])
                command_list.extend(["--chdir", "/tmp/workspace"])
                for key, value in isolated_env.items():
                    sandbox_value = value
                    if key == "HOME":
                        sandbox_value = f"/tmp/{sandbox_home.name}"
                    elif key == "TMPDIR":
                        sandbox_value = "/tmp"
                    command_list.extend(["--setenv", key, sandbox_value])
                command_list.extend(["--setenv", "CAIOS_EGRESS_BLOCKED", "true"])
                command_list.extend(args)
                command = tuple(command_list)
            try:
                proc = subprocess.run(
                    command,
                    cwd=Path("/") if block_egress else worktree,
                    env=sandbox_env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                    pass_fds=pass_fds,
                )
            finally:
                if seccomp_file is not None:
                    seccomp_file.close()
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

            if require_egress_block:
                isolated_workspace = sandbox_tmp / "workspace"
                shutil.copytree(worktree, isolated_workspace, symlinks=True)
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

import os
import shutil
from pathlib import Path
import subprocess
import uuid

import pytest

from autonomy.sandbox_simulator import DisposableWorktree


@pytest.mark.skipif(
    subprocess.run(("git", "--version"), capture_output=True).returncode != 0,
    reason="git is required",
)
def test_disposable_worktree_simulates_valid_patch(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(("git", "init"), cwd=repo, capture_output=True, check=True)
    subprocess.run(("git", "config", "user.email", "caios@test"), cwd=repo, check=True)
    subprocess.run(("git", "config", "user.name", "CAIOS Test"), cwd=repo, check=True)
    (repo / "value.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=repo, check=True)
    subprocess.run(("git", "commit", "-m", "base"), cwd=repo, capture_output=True, check=True)

    patch = """diff --git a/value.txt b/value.txt
index 43dd47b..9d3f98f 100644
--- a/value.txt
+++ b/value.txt
@@ -1 +1 @@
-one
+two
"""
    result = DisposableWorktree(repo).run(
        patch,
        ("python", "-c", "print(open('value.txt').read().strip())"),
    )
    assert result.status == "PASS", result.as_dict()
    assert result.validation_returncode == 0
    assert (repo / "value.txt").read_text(encoding="utf-8") == "one\n"


@pytest.mark.skipif(
    subprocess.run(("git", "--version"), capture_output=True).returncode != 0,
    reason="git is required",
)
def test_disposable_worktree_rejects_bad_patch(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(("git", "init"), cwd=repo, capture_output=True, check=True)
    subprocess.run(("git", "config", "user.email", "caios@test"), cwd=repo, check=True)
    subprocess.run(("git", "config", "user.name", "CAIOS Test"), cwd=repo, check=True)
    (repo / "value.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=repo, check=True)
    subprocess.run(("git", "commit", "-m", "base"), cwd=repo, capture_output=True, check=True)

    result = DisposableWorktree(repo).run(
        "this is not a patch\n",
        ("python", "-c", "raise SystemExit(0)"),
    )
    assert result.status == "FAIL"
    assert result.validation_returncode is None



@pytest.mark.skipif(
    subprocess.run(("git", "--version"), capture_output=True).returncode != 0,
    reason="git is required",
)
def test_disposable_validation_does_not_inherit_ambient_secrets(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(("git", "init"), cwd=repo, capture_output=True, check=True)
    subprocess.run(("git", "config", "user.email", "caios@test"), cwd=repo, check=True)
    subprocess.run(("git", "config", "user.name", "CAIOS Test"), cwd=repo, check=True)
    (repo / "value.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=repo, check=True)
    subprocess.run(("git", "commit", "-m", "base"), cwd=repo, capture_output=True, check=True)

    monkeypatch.setenv("CAIOS_TEST_SECRET", "must-not-reach-candidate")
    monkeypatch.setenv("GH_TOKEN", "must-not-reach-candidate")
    patch = """diff --git a/value.txt b/value.txt
--- a/value.txt
+++ b/value.txt
@@ -1 +1 @@
-one
+two
"""
    result = DisposableWorktree(repo).run(
        patch,
        (
            "python",
            "-c",
            "import os; raise SystemExit(1 if any(k in os.environ for k in ('CAIOS_TEST_SECRET', 'GH_TOKEN')) else 0)",
        ),
    )
    assert result.status == "PASS"
    assert result.validation_returncode == 0


@pytest.mark.skipif(
    subprocess.run(("git", "--version"), capture_output=True).returncode != 0,
    reason="git is required",
)
def test_disposable_validation_uses_temporary_home(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(("git", "init"), cwd=repo, capture_output=True, check=True)
    subprocess.run(("git", "config", "user.email", "caios@test"), cwd=repo, check=True)
    subprocess.run(("git", "config", "user.name", "CAIOS Test"), cwd=repo, check=True)
    (repo / "value.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=repo, check=True)
    subprocess.run(("git", "commit", "-m", "base"), cwd=repo, capture_output=True, check=True)

    patch = """diff --git a/value.txt b/value.txt
--- a/value.txt
+++ b/value.txt
@@ -1 +1 @@
-one
+two
"""
    result = DisposableWorktree(repo).run(
        patch,
        (
            "python",
            "-c",
            "import os; from pathlib import Path; raise SystemExit(0 if Path.home().name.startswith('caios-home-') else 1)",
        ),
    )
    assert result.status == "PASS"



@pytest.mark.skipif(
    os.environ.get("CAIOS_EGRESS_BLOCKED") == "true",
    reason="Do not recursively create a Docker sandbox from inside the egress-blocked validation process",
)
@pytest.mark.skipif(
    not os.environ.get("CAIOS_SANDBOX_IMAGE"),
    reason="Run only after the trusted sandbox image has been built",
)
@pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="Docker is required for network-isolated validation",
)
@pytest.mark.skipif(
    subprocess.run(("git", "--version"), capture_output=True).returncode != 0,
    reason="git is required",
)
def test_docker_network_none_blocks_access_to_bridge_service(tmp_path: Path):
    docker = shutil.which("docker")
    image = os.environ["CAIOS_SANDBOX_IMAGE"]
    network = f"caios-test-{uuid.uuid4().hex[:12]}"
    server_name = f"caios-server-{uuid.uuid4().hex[:12]}"

    created = subprocess.run(
        (docker, "network", "create", network),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert created.returncode == 0, created.stderr

    try:
        server = subprocess.run(
            (
                docker, "run", "--detach", "--name", server_name,
                "--network", network,
                image, "python3", "-m", "http.server", "8765", "--bind", "0.0.0.0",
            ),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert server.returncode == 0, server.stderr

        inspect = subprocess.run(
            (docker, "inspect", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", server_name),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        server_ip = inspect.stdout.strip()
        assert inspect.returncode == 0 and server_ip, inspect.stderr

        # Positive control: the endpoint is genuinely reachable from an
        # ordinary container attached to the same bridge.
        positive = subprocess.run(
            (
                docker, "run", "--rm", "--network", network, image, "python", "-c",
                f"import socket; s=socket.create_connection(({server_ip!r}, 8765), timeout=3); s.close()",
            ),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert positive.returncode == 0, positive.stderr

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(("git", "init"), cwd=repo, capture_output=True, check=True)
        subprocess.run(("git", "config", "user.email", "caios@test"), cwd=repo, check=True)
        subprocess.run(("git", "config", "user.name", "CAIOS Test"), cwd=repo, check=True)
        (repo / "value.txt").write_text("one\n", encoding="utf-8")
        subprocess.run(("git", "add", "."), cwd=repo, check=True)
        subprocess.run(("git", "commit", "-m", "base"), cwd=repo, capture_output=True, check=True)

        patch = """diff --git a/value.txt b/value.txt
--- a/value.txt
+++ b/value.txt
@@ -1 +1 @@
-one
+two
"""
        command = (
            "python",
            "-c",
            (
                "import socket,sys\n"
                f"target={server_ip!r}\n"
                "try:\n"
                "    s=socket.create_connection((target, 8765), timeout=2)\n"
                "    s.close()\n"
                "except OSError:\n"
                "    sys.exit(0)\n"
                "else:\n"
                "    sys.exit(9)\n"
            ),
        )
        result = DisposableWorktree(repo).run(
            patch,
            command,
            require_egress_block=True,
        )
        assert result.status == "PASS", result.as_dict()
        assert result.egress_blocked is True
    finally:
        subprocess.run((docker, "rm", "--force", server_name), capture_output=True, text=True, timeout=20, check=False)
        subprocess.run((docker, "network", "rm", network), capture_output=True, text=True, timeout=20, check=False)



@pytest.mark.skipif(
    subprocess.run(("git", "--version"), capture_output=True).returncode != 0,
    reason="git is required",
)
def test_egress_block_fails_closed_if_sandbox_image_is_missing(tmp_path: Path, monkeypatch):
    import autonomy.sandbox_simulator as simulator

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(("git", "init"), cwd=repo, capture_output=True, check=True)
    subprocess.run(("git", "config", "user.email", "caios@test"), cwd=repo, check=True)
    subprocess.run(("git", "config", "user.name", "CAIOS Test"), cwd=repo, check=True)
    (repo / "value.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=repo, check=True)
    subprocess.run(("git", "commit", "-m", "base"), cwd=repo, capture_output=True, check=True)

    real_which = shutil.which
    real_run = subprocess.run

    def fake_which(name):
        return "/usr/bin/docker" if name == "docker" else real_which(name)

    def fake_run(args, *pargs, **kwargs):
        if isinstance(args, (tuple, list)) and len(args) >= 3 and args[1:3] == ("image", "inspect"):
            return subprocess.CompletedProcess(args, 1, "", "trusted sandbox image missing")
        return real_run(args, *pargs, **kwargs)

    monkeypatch.setattr(simulator.shutil, "which", fake_which)
    monkeypatch.setattr(simulator.subprocess, "run", fake_run)
    monkeypatch.setenv("CAIOS_SANDBOX_IMAGE", "caios-validation-sandbox:missing-test-image")

    patch = """diff --git a/value.txt b/value.txt
--- a/value.txt
+++ b/value.txt
@@ -1 +1 @@
-one
+two
"""
    result = DisposableWorktree(repo).run(
        patch,
        ("python", "-c", "raise SystemExit(0)"),
        require_egress_block=True,
    )

    assert result.status == "FAIL"
    assert result.validation_returncode == 127
    assert "egress-block-unavailable:sandbox-image-not-built" in result.stderr_tail
    assert result.egress_blocked is False


@pytest.mark.skipif(
    subprocess.run(("git", "--version"), capture_output=True).returncode != 0,
    reason="git is required",
)
def test_egress_block_fails_closed_if_docker_is_unavailable(tmp_path: Path, monkeypatch):
    import autonomy.sandbox_simulator as simulator

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(("git", "init"), cwd=repo, capture_output=True, check=True)
    subprocess.run(("git", "config", "user.email", "caios@test"), cwd=repo, check=True)
    subprocess.run(("git", "config", "user.name", "CAIOS Test"), cwd=repo, check=True)
    (repo / "value.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=repo, check=True)
    subprocess.run(("git", "commit", "-m", "base"), cwd=repo, capture_output=True, check=True)

    monkeypatch.setattr(simulator.shutil, "which", lambda _name: None)
    patch = """diff --git a/value.txt b/value.txt
--- a/value.txt
+++ b/value.txt
@@ -1 +1 @@
-one
+two
"""
    result = DisposableWorktree(repo).run(
        patch,
        ("python", "-c", "raise SystemExit(0)"),
        require_egress_block=True,
    )

    assert result.status == "FAIL"
    assert result.validation_returncode == 127
    assert "egress-block-unavailable:docker-not-installed" in result.stderr_tail
    assert result.egress_blocked is False

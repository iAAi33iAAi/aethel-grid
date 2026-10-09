import os
import shutil
import socket
import threading
from pathlib import Path
import subprocess

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
def test_docker_network_none_validation_cannot_reach_host_loopback(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(("git", "init"), cwd=repo, capture_output=True, check=True)
    subprocess.run(("git", "config", "user.email", "caios@test"), cwd=repo, check=True)
    subprocess.run(("git", "config", "user.name", "CAIOS Test"), cwd=repo, check=True)
    (repo / "value.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=repo, check=True)
    subprocess.run(("git", "commit", "-m", "base"), cwd=repo, capture_output=True, check=True)

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    reached = {"value": False}

    def accept_once():
        listener.settimeout(2.0)
        try:
            conn, _ = listener.accept()
            reached["value"] = True
            conn.close()
        except (TimeoutError, OSError):
            pass

    thread = threading.Thread(target=accept_once, daemon=True)
    thread.start()
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
            f"port={port}\n"
            "try:\n"
            "    s=socket.socket()\n"
            "    s.settimeout(1)\n"
            "    s.connect(('127.0.0.1', port))\n"
            "except OSError:\n"
            "    sys.exit(0)\n"
            "else:\n"
            "    sys.exit(9)\n"
        ),
    )
    try:
        result = DisposableWorktree(repo).run(
            patch,
            command,
            require_egress_block=True,
        )
    finally:
        listener.close()
        thread.join(timeout=3)

    assert result.status == "PASS", result.as_dict()
    assert result.egress_blocked is True
    assert reached["value"] is False


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

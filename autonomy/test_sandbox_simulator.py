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
    assert result.status == "PASS"
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
            "import os; from pathlib import Path; raise SystemExit(0 if Path.home().name == '.caios-home' else 1)",
        ),
    )
    assert result.status == "PASS"

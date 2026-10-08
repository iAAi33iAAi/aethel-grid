from pathlib import Path
import json

from integrations.tool_compiler import compile_command


def test_registered_command_compiles(tmp_path: Path, monkeypatch):
    (tmp_path / "integrations").mkdir()
    (tmp_path / "integrations/caios_tool_registry.json").write_text(
        json.dumps({
            "policy": {},
            "tools": [
                {
                    "id": "echo",
                    "capability": "test",
                    "authority": "deterministic",
                    "license": "MIT",
                    "command": ["python", "-c", "print('ok')"]
                }
            ]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/python")
    compiled, reason = compile_command(tmp_path, "echo", ("somefile.txt",))
    assert reason == "compiled"
    assert compiled is not None
    assert compiled.argv[-1] == "somefile.txt"
    assert len(compiled.command_digest) == 64


def test_unregistered_command_is_denied(tmp_path: Path):
    (tmp_path / "integrations").mkdir()
    (tmp_path / "integrations/caios_tool_registry.json").write_text(
        json.dumps({"policy": {}, "tools": []}),
        encoding="utf-8",
    )
    compiled, reason = compile_command(tmp_path, "missing")
    assert compiled is None
    assert reason == "tool-not-registered"


def test_undeclared_command_is_denied(tmp_path: Path):
    (tmp_path / "integrations").mkdir()
    (tmp_path / "integrations/caios_tool_registry.json").write_text(
        json.dumps({
            "policy": {},
            "tools": [
                {"id": "echo", "capability": "test", "authority": "deterministic", "license": "MIT"}
            ]
        }),
        encoding="utf-8",
    )
    compiled, reason = compile_command(tmp_path, "echo")
    assert compiled is None
    assert reason == "tool-command-not-declared"


def test_path_argument_cannot_escape_repository(tmp_path: Path, monkeypatch):
    (tmp_path / "integrations").mkdir()
    (tmp_path / "integrations/caios_tool_registry.json").write_text(
        json.dumps({
            "policy": {},
            "tools": [{
                "id": "pytest",
                "capability": "verification",
                "authority": "deterministic",
                "license": "MIT",
                "command": ["python", "-m", "pytest", "-q"],
                "argument_policy": "path-only"
            }]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/python")
    compiled, reason = compile_command(tmp_path, "pytest", ("../outside",))
    assert compiled is None
    assert reason == "tool-argument-escapes-repository"


def test_none_policy_rejects_extra_args(tmp_path: Path, monkeypatch):
    (tmp_path / "integrations").mkdir()
    (tmp_path / "integrations/caios_tool_registry.json").write_text(
        json.dumps({
            "policy": {},
            "tools": [{
                "id": "echo",
                "capability": "test",
                "authority": "deterministic",
                "license": "MIT",
                "command": ["python", "-c", "print('ok')"]
            }]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/python")
    compiled, reason = compile_command(tmp_path, "echo", ("arg",))
    assert compiled is None
    assert reason == "tool-arguments-not-permitted"

import json
from pathlib import Path

from autonomy.protocol_admission import ProtocolRegistry
from autonomy.protocol_conformance import ProtocolConformanceRunner


def write_fixture(tmp_path: Path):
    (tmp_path / "autonomy").mkdir()
    (tmp_path / "integrations").mkdir()
    (tmp_path / "autonomy/protocol_registry.json").write_text(
        json.dumps({
            "policy": {"unknown_protocol":"REJECT","draft_protocol_requires_opt_in":True,"major_version_mismatch":"REJECT"},
            "protocols": [
                {
                    "id":"a2a",
                    "latest_known_revision":"1.0.0",
                    "status":"stable",
                    "transport_role":"agent-to-agent",
                    "license":"Apache-2.0",
                    "source_url":"https://a2a-protocol.org/latest/",
                    "draft":False
                }
            ]
        }),
        encoding="utf-8",
    )
    (tmp_path / "integrations/caios_tool_registry.json").write_text(
        json.dumps({
            "policy": {},
            "tools": [
                {
                    "id":"a2a-cli",
                    "capability":"agent-to-agent-discovery",
                    "authority":"evidence",
                    "license":"Apache-2.0",
                    "command":["a2a","version"]
                }
            ]
        }),
        encoding="utf-8",
    )


def test_protocol_registry_admits_exact_revision(tmp_path: Path):
    write_fixture(tmp_path)
    registry = ProtocolRegistry(tmp_path)
    assert registry.admit("a2a","1.0.0")[0] is True
    assert registry.admit("a2a","0.3.0")[0] is False


def test_protocol_conformance_plan_is_explicit(tmp_path: Path, monkeypatch):
    write_fixture(tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/"+name)
    rows = ProtocolConformanceRunner(tmp_path).plan()
    assert rows[0]["protocol"] == "a2a"
    assert rows[0]["conformance"] == "CONFIGURED"

from pathlib import Path
import json

import pytest

from autonomy.protocol_peer import admit_peer, from_a2a_card, from_acp_initialize


def write_registry(tmp_path: Path):
    (tmp_path / "autonomy").mkdir()
    (tmp_path / "autonomy/protocol_registry.json").write_text(
        json.dumps({
            "policy": {
                "unknown_protocol":"REJECT",
                "draft_protocol_requires_opt_in":True,
                "major_version_mismatch":"REJECT"
            },
            "protocols": [
                {
                    "id":"acp",
                    "latest_known_revision":"1",
                    "status":"stable",
                    "transport_role":"agent-client",
                    "license":"Apache-2.0",
                    "source_url":"https://github.com/agentclientprotocol/agent-client-protocol",
                    "draft":False
                },
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


def test_acp_initialize_normalizes():
    peer = from_acp_initialize({
        "result": {
            "protocolVersion": 1,
            "agentInfo": {"name":"coder","version":"2.0"},
            "capabilities": {"session": {}},
            "authMethods": []
        }
    })
    assert peer.protocol == "acp"
    assert peer.protocol_version == "1"
    assert peer.name == "coder"


def test_a2a_card_normalizes():
    peer = from_a2a_card({
        "name":"builder",
        "version":"1.2",
        "supportedInterfaces":[{"url":"https://example.com","protocolBindingVersion":"1.0.0"}],
        "capabilities":{"streaming":True},
        "securitySchemes":{"oauth2":{}}
    })
    assert peer.protocol == "a2a"
    assert peer.protocol_version == "1.0.0"
    assert peer.capabilities["capability_count"] == 1


def test_peer_admission_checks_registry(tmp_path: Path):
    write_registry(tmp_path)
    peer = from_a2a_card({
        "name":"builder",
        "version":"1.2",
        "supportedInterfaces":[{"url":"https://example.com","protocolBindingVersion":"1.0.0"}],
    })
    assert admit_peer(tmp_path, peer)[0] is True
    bad = from_a2a_card({
        "name":"builder",
        "version":"1.2",
        "supportedInterfaces":[{"url":"https://example.com","protocolBindingVersion":"0.3.0"}],
    })
    assert admit_peer(tmp_path, bad)[0] is False

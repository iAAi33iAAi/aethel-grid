import json
from pathlib import Path

from autonomy.protocol_peer import PeerDescriptor
from autonomy.route_selector import select_route


def root_with_protocols(tmp_path: Path) -> Path:
    (tmp_path / "autonomy").mkdir()
    (tmp_path / "autonomy/protocol_registry.json").write_text(
        json.dumps({
            "policy":{"draft_protocol_requires_opt_in":True},
            "protocols":[
                {
                    "id":"acp","latest_known_revision":"1","status":"stable",
                    "transport_role":"agent-client","license":"Apache-2.0",
                    "source_url":"https://github.com/agentclientprotocol/agent-client-protocol","draft":False
                },
                {
                    "id":"a2a","latest_known_revision":"1.0.0","status":"stable",
                    "transport_role":"agent-to-agent","license":"Apache-2.0",
                    "source_url":"https://a2a-protocol.org/latest/","draft":False
                },
                {
                    "id":"mcp","latest_known_revision":"2026-07-28","status":"final",
                    "transport_role":"agent-to-tool-context","license":"MIT",
                    "source_url":"https://modelcontextprotocol.io/","draft":False
                }
            ]
        }),
        encoding="utf-8",
    )
    return tmp_path


def test_route_selector_prefers_acp_for_coding(tmp_path: Path):
    root = root_with_protocols(tmp_path)
    peers = [
        PeerDescriptor("mcp:x:1","mcp","2026-07-28","x","1",{"capabilities":{}},{},{}),
        PeerDescriptor("acp:y:1","acp","1","y","1",{"capabilities":{"session":{}}},{},{}),
    ]
    result = select_route(root, peers, purpose="coding")
    assert result.protocol == "acp"
    assert result.status == "ELIGIBLE"


def test_route_selector_blocks_unadmitted_revision(tmp_path: Path):
    root = root_with_protocols(tmp_path)
    peers = [
        PeerDescriptor("a2a:x:0","a2a","0.3","x","1",{"capabilities":{}},{},{}),
    ]
    result = select_route(root, peers, purpose="agent-to-agent")
    assert result.status == "BLOCKED"

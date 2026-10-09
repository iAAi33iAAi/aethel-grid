import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from autonomy.multi_agent_provider import EndpointSpec, MultiAgentProposalProvider


class FakeProvider:
    def __init__(self, endpoint, model, api_key=None):
        self.endpoint = endpoint
        self.model = model

    def propose(self, snapshot):
        return [{"kind": "run_test", "target": ".", "risk": 0.1}]


def test_multi_agent_provider_normalizes_identity():
    provider = MultiAgentProposalProvider(
        (
            EndpointSpec(
                agent_id="a",
                endpoint="https://example.invalid/a",
                model="m-a",
                model_revision="rev-a",
                protocol="openai-compatible",
                agent_version="1",
                source_ref="git:a",
            ),
            EndpointSpec(
                agent_id="b",
                endpoint="https://example.invalid/b",
                model="m-b",
                model_revision="rev-b",
                protocol="openai-compatible",
                agent_version="1",
                source_ref="git:b",
            ),
        ),
        provider_factory=FakeProvider,
    )
    rows = provider.propose({"state": "x"})
    assert {row["agent_id"] for row in rows} == {"a", "b"}
    assert all(row["protocol"] == "openai-compatible" for row in rows)
    assert {row["model_revision"] for row in rows} == {"rev-a", "rev-b"}



@pytest.mark.skipif(os.environ.get("CAIOS_EGRESS_BLOCKED") == "true", reason="network sockets are denied during candidate validation")
def test_openai_compatible_provider_does_not_follow_redirects():
    from autonomy.caios_runtime import OpenAICompatibleProposalProvider

    state = {"approved_requests": 0, "redirect_target_requests": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            if self.path == "/approved":
                state["approved_requests"] += 1
                self.send_response(302)
                self.send_header("Location", "/redirect-target")
                self.end_headers()
            elif self.path == "/redirect-target":
                state["redirect_target_requests"] += 1
                payload = b'{"proposals": []}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/approved"
        provider = OpenAICompatibleProposalProvider(
            endpoint,
            "test-model",
            api_key="test-secret",
            send_source_context=True,
        )
        with pytest.raises(Exception) as err:
            provider.propose({"state": "test", "source_context": "bounded fixture"})

        assert state["approved_requests"] == 1
        assert state["redirect_target_requests"] == 0
        assert "HTTP Error 302" in str(err.value)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

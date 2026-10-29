import json
import os
import threading
from pathlib import Path

from ops.agent_colony.collaboration import build_role_task_contexts
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



def test_provider_fans_out_role_specific_toolboxes_concurrently():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "ops" / "agent_colony" / "manifest.json").read_text(encoding="utf-8"))
    tasks = build_role_task_contexts(
        manifest,
        agent_bindings={
            "provider-protocol": "protocol_analyst",
            "provider-security": "security_analyst",
        },
        source_revision="a" * 40,
        findings=[{
            "id": "AC-01", "severity": "high", "title": "fixture finding",
            "evidence_path": "conformance/GATE_STATUS.json", "details": "SHOULD_NOT_BE_SENT",
        }],
    )
    barrier = threading.Barrier(2)
    observed = {}
    lock = threading.Lock()

    class TaskCaptureProvider:
        def __init__(self, endpoint, model, api_key=None):
            self.model = model

        def propose(self, snapshot):
            barrier.wait(timeout=5)
            with lock:
                observed[self.model] = snapshot["agent_task"]
            return [{"kind": "review_finding", "target": self.model, "risk": 0.1}]

    provider = MultiAgentProposalProvider(
        (
            EndpointSpec(
                agent_id="provider-protocol", endpoint="https://example.invalid/protocol",
                model="model-protocol", model_revision="fixture-1", protocol="openai-compatible",
                agent_version="1", source_ref="git:" + "1" * 40,
            ),
            EndpointSpec(
                agent_id="provider-security", endpoint="https://example.invalid/security",
                model="model-security", model_revision="fixture-1", protocol="openai-compatible",
                agent_version="1", source_ref="git:" + "2" * 40,
            ),
        ),
        provider_factory=TaskCaptureProvider,
        max_workers=2,
    )
    proposals = provider.propose(
        {"source_revision": "a" * 40, "evidence_mode": "metadata-only"},
        task_contexts=tasks,
    )

    assert len(proposals) == 2
    assert not provider.last_errors
    assert observed["model-protocol"]["role_id"] == "protocol_analyst"
    assert observed["model-security"]["role_id"] == "security_analyst"
    assert "read_specs" in observed["model-protocol"]["toolbox"]["allow"]
    assert "inspect_auth_code" in observed["model-security"]["toolbox"]["allow"]
    assert "read_secret_values" in observed["model-security"]["toolbox"]["deny"]
    assert all(item["egress_policy"]["tool_execution_authority"] is False for item in observed.values())
    assert all("details" not in item["input_findings"][0] for item in observed.values())
    assert "SHOULD_NOT_BE_SENT" not in json.dumps(observed)


def test_multi_agent_provider_rejects_task_context_for_unknown_endpoint():
    provider = MultiAgentProposalProvider((), provider_factory=FakeProvider)
    with pytest.raises(ValueError, match="unconfigured agent IDs"):
        provider.propose({"source_revision": "x"}, task_contexts={"unregistered": {"role_id": "security_analyst"}})


def test_multi_agent_provider_rejects_non_mapping_task_contexts():
    provider = MultiAgentProposalProvider((), provider_factory=FakeProvider)
    with pytest.raises(ValueError, match="task_contexts must map"):
        provider.propose({"source_revision": "x"}, task_contexts=[])

from autonomy.caios_runtime import MAX_PROVIDER_PROPOSALS, MAX_PROVIDER_RESPONSE_BYTES, OpenAICompatibleProposalProvider


def test_provider_strips_source_context_by_default(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size=-1):
            captured["read_size"] = size
            captured["body"] = b'{"proposals":[]}'
            return captured["body"][:size] if size >= 0 else captured["body"]

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return Response()

    provider = OpenAICompatibleProposalProvider(
        "https://example.com/v1/chat/completions",
        "test-model",
    )
    monkeypatch.setattr(provider.opener, "open", fake_urlopen)
    provider.propose({
        "snapshot": {"head": "abc"},
        "gaps": {"verification": 1.0},
        "source_context": {"files": [{"path": "src/main.py", "content": "SECRET? no"}]},
    })

    import json
    body = json.loads(captured["request"].data.decode("utf-8"))
    message = body["messages"][1]["content"]
    assert "source_context" not in message


def test_provider_can_send_opted_in_context(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size=-1):
            return b'{"proposals":[]}'[:size] if size >= 0 else b'{"proposals":[]}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return Response()

    provider = OpenAICompatibleProposalProvider(
        "https://example.com/v1/chat/completions",
        "test-model",
        send_source_context=True,
    )
    monkeypatch.setattr(provider.opener, "open", fake_urlopen)
    provider.propose({
        "snapshot": {"head": "abc"},
        "gaps": {"verification": 1.0},
        "source_context": {"files": [{"path": "src/main.py", "content": "hello"}]},
    })

    import json
    body = json.loads(captured["request"].data.decode("utf-8"))
    message = body["messages"][1]["content"]
    assert "source_context" in message


def test_provider_bounds_response_bytes_before_json_parsing(monkeypatch):
    class OversizedResponse:
        def __init__(self):
            self.read_size = None
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size=-1):
            self.read_size = size
            return b"x" * size

    response = OversizedResponse()
    provider = OpenAICompatibleProposalProvider("https://example.com/v1/chat/completions", "test-model")
    monkeypatch.setattr(provider.opener, "open", lambda request, timeout: response)

    import pytest
    with pytest.raises(ValueError, match="exceeds maximum byte size"):
        provider.propose({"snapshot": {"head": "abc"}})
    assert response.read_size == MAX_PROVIDER_RESPONSE_BYTES + 1


def test_provider_rejects_non_array_proposals(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size=-1):
            payload = b'{"proposals":"not-an-array"}'
            return payload[:size] if size >= 0 else payload

    provider = OpenAICompatibleProposalProvider("https://example.com/v1/chat/completions", "test-model")
    monkeypatch.setattr(provider.opener, "open", lambda request, timeout: Response())
    import pytest
    with pytest.raises(ValueError, match="proposals field must be a JSON array"):
        provider.propose({"snapshot": {"head": "abc"}})


def test_provider_caps_proposal_count_and_discards_non_object_rows(monkeypatch):
    import json
    rows = [{"kind": "observe", "index": i} for i in range(MAX_PROVIDER_PROPOSALS + 5)]
    rows.insert(3, "not-an-object")
    payload = json.dumps({"proposals": rows}).encode("utf-8")

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size=-1): return payload[:size] if size >= 0 else payload

    provider = OpenAICompatibleProposalProvider("https://example.com/v1/chat/completions", "test-model")
    monkeypatch.setattr(provider.opener, "open", lambda request, timeout: Response())
    proposals = provider.propose({"snapshot": {"head": "abc"}})
    assert len(proposals) == MAX_PROVIDER_PROPOSALS
    assert all(isinstance(row, dict) for row in proposals)


def test_provider_rejects_endpoint_credentials_query_fragment_and_bad_port():
    import pytest
    invalid_urls = [
        "https://user:secret@example.com/v1/chat/completions",
        "https://example.com/v1/chat/completions?token=secret",
        "https://example.com/v1/chat/completions#fragment",
        "https://example.com:invalid/v1/chat/completions",
    ]
    for url in invalid_urls:
        with pytest.raises(ValueError):
            OpenAICompatibleProposalProvider(url, "test-model")


def test_provider_does_not_inherit_environment_proxy_settings(monkeypatch):
    import urllib.request
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.attacker.invalid:3128")
    monkeypatch.setenv("https_proxy", "http://proxy.attacker.invalid:3128")
    provider = OpenAICompatibleProposalProvider(
        "https://example.com/v1/chat/completions",
        "test-model",
    )
    proxy_handlers = [
        handler for handler in provider.opener.handlers
        if isinstance(handler, urllib.request.ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}


def test_provider_rejects_invalid_chat_completion_shape(monkeypatch):
    import pytest
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size=-1):
            payload = b'{"choices":[]}'
            return payload[:size] if size >= 0 else payload
    provider = OpenAICompatibleProposalProvider(
        "https://example.com/v1/chat/completions",
        "test-model",
    )
    monkeypatch.setattr(provider.opener, "open", lambda request, timeout: Response())
    with pytest.raises(ValueError, match="choices response has an invalid shape"):
        provider.propose({"snapshot": {"head": "abc"}})

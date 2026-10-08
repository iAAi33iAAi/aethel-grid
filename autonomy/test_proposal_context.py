from autonomy.caios_runtime import OpenAICompatibleProposalProvider


def test_provider_strips_source_context_by_default(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            captured["body"] = b'{"proposals":[]}'
            return captured["body"]

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = OpenAICompatibleProposalProvider(
        "https://example.com/v1/chat/completions",
        "test-model",
    )
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
        def read(self):
            return b'{"proposals":[]}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = OpenAICompatibleProposalProvider(
        "https://example.com/v1/chat/completions",
        "test-model",
        send_source_context=True,
    )
    provider.propose({
        "snapshot": {"head": "abc"},
        "gaps": {"verification": 1.0},
        "source_context": {"files": [{"path": "src/main.py", "content": "hello"}]},
    })

    import json
    body = json.loads(captured["request"].data.decode("utf-8"))
    message = body["messages"][1]["content"]
    assert "source_context" in message

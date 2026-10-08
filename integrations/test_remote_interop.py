from integrations.remote_interop import EXPECTED_PROTOCOL, InteropEvidence, validate_endpoint


def test_interop_response_requires_canonical_protocol():
    good = {
        "protocol": EXPECTED_PROTOCOL,
        "service": "caios",
        "version": "1",
        "request_id": "r1",
        "status": "PASS",
        "decision": "OK",
        "reasons": [],
        "result": {},
        "evidence": {},
    }
    parsed = InteropEvidence.from_json(good)
    assert parsed.response_digest

    bad = dict(good, protocol="wrong/1")
    try:
        InteropEvidence.from_json(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("protocol mismatch must be rejected")


def test_remote_nonlocal_http_is_rejected():
    try:
        validate_endpoint("http://example.com/evaluate")
    except ValueError:
        pass
    else:
        raise AssertionError("remote plaintext endpoint must be rejected")


def test_remote_client_uses_aethel_v1_evaluate_path(monkeypatch):
    from integrations.remote_interop import InteropEvidence, RemoteInteropClient

    captured = {}

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limit=-1):
            captured["read_limit"] = limit
            return (
                b'{"protocol":"aethel-interop/1","service":"x","version":"1",'
                b'"request_id":"r","status":"PASS","decision":"OK",'
                b'"reasons":[],"result":{},"evidence":{}}'
            )

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.method
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = RemoteInteropClient("https://example.com")
    response = client.evaluate("r", "capabilities", {})
    assert isinstance(response, InteropEvidence)
    assert captured["url"] == "https://example.com/aethel/evaluate"
    assert captured["method"] == "POST"

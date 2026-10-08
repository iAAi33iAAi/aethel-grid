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

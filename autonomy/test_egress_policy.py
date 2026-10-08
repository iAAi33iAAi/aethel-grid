from autonomy.egress_policy import EgressPolicy, scan_context


def test_source_context_is_blocked_by_default():
    result = scan_context({"source_context":"safe code"}, EgressPolicy())
    assert result.status == "BLOCKED"
    assert "source-context-egress-disabled-by-default" in result.reasons


def test_credential_like_material_is_blocked():
    policy = EgressPolicy(allow_source_context=True)
    result = scan_context({"source_context":"api_key=supersecretvalue"}, policy)
    assert result.status == "BLOCKED"
    assert "credential-like-material-detected" in result.reasons


def test_allowed_non_source_payload_passes():
    result = EgressPolicy().inspect('{"gaps":{"verification":0.5}}')
    assert result.status == "ALLOW"

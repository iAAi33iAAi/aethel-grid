from interop.aethel_service import evaluate


def test_state_rebuild_is_deterministic():
    events = [
        {"id": "b", "parents": ["a"], "state": {"x": 2}},
        {"id": "a", "parents": [], "state": {"x": 1, "y": 3}},
    ]
    result = evaluate("r1", "state-rebuild", {"events": events})
    assert result["status"] == "PASS"
    assert result["result"]["state"] == {"x": 2, "y": 3}
    assert result["result"]["ordered_event_ids"] == ["a", "b"]


def test_cycle_fails_closed():
    events = [
        {"id": "a", "parents": ["b"], "state": {}},
        {"id": "b", "parents": ["a"], "state": {}},
    ]
    result = evaluate("r2", "state-rebuild", {"events": events})
    assert result["status"] == "FAIL"


def test_canonical_conformance_remains_blocked():
    result = evaluate("r3", "conformance-status", {})
    assert result["status"] == "BLOCKED"
    assert result["decision"] == "HOLD"


def test_missing_parent_fails_closed():
    result = evaluate("r4", "state-rebuild", {"events": [{"id": "b", "parents": ["missing"], "state": {}}]})
    assert result["status"] == "FAIL"

def test_health_is_healthy_while_conformance_is_blocked():
    result = evaluate("health", "conformance-status", {})
    assert result["status"] == "BLOCKED"

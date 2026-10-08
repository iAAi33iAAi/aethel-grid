from pathlib import Path

from autonomy.circuit_breaker import CircuitBreaker


def test_circuit_breaker_quarantines_repeated_failures(tmp_path: Path):
    breaker = CircuitBreaker(tmp_path / "circuit.json", failure_budget=2)
    state = "a" * 64
    action = "b" * 64

    assert breaker.allowed(state, action) == (True, "not-recorded")
    first = breaker.record(state, action, "FAIL")
    assert first.quarantined is False
    second = breaker.record(state, action, "FAIL")
    assert second.quarantined is True
    assert breaker.allowed(state, action) == (False, "quarantined")


def test_state_change_breaks_quarantine_key(tmp_path: Path):
    breaker = CircuitBreaker(tmp_path / "circuit.json", failure_budget=1)
    breaker.record("a"*64, "b"*64, "FAIL")
    assert breaker.allowed("c"*64, "b"*64) == (True, "not-recorded")

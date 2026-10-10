"""Defensive candidate adapter for SPEC-004:v0.3.1_METRIC_LAW.

This module preserves the recovered equation but adds input, type, domain and
width validation. It is noncanonical until the project ratifies this candidate
input profile and independently verifies Rust/Python conformance.
"""
from __future__ import annotations
from typing import Any, Sequence
import json

Q = 1_000_000
T_PROCEED = 100_000
T_REVIEW = 900_000
I64_MIN = -(1 << 63)
I64_MAX = (1 << 63) - 1
I128_MIN = -(1 << 127)
I128_MAX = (1 << 127) - 1

ROTATION_TABLE = {
    0: (1_000_000, 0), 15: (965_926, 258_819), 30: (866_025, 500_000),
    45: (707_107, 707_107), 60: (500_000, 866_025), 90: (0, 1_000_000),
    180: (-1_000_000, 0), 270: (0, -1_000_000),
}

def _integer(value: Any, *, label: str) -> int:
    if type(value) is not int:  # bool is deliberately excluded
        raise TypeError(f"{label} must be an integer, not {type(value).__name__}")
    return value

def _i64(value: Any, *, label: str) -> int:
    value = _integer(value, label=label)
    if value < I64_MIN or value > I64_MAX:
        raise OverflowError(f"{label} is outside signed i64 range")
    return value

def _i128(value: Any, *, label: str) -> int:
    value = _integer(value, label=label)
    if value < I128_MIN or value > I128_MAX:
        raise OverflowError(f"{label} is outside signed i128 range")
    return value

def qdiv(numerator: int, denominator: int) -> int:
    """Signed integer division truncated toward zero; zero divisor fails closed."""
    numerator = _i128(numerator, label="numerator")
    denominator = _i128(denominator, label="denominator")
    if denominator == 0:
        raise ZeroDivisionError("SPEC-004 qdiv denominator must be nonzero")
    quotient = (abs(numerator) // abs(denominator)) * (
        -1 if (numerator < 0) ^ (denominator < 0) else 1
    )
    return _i128(quotient, label="qdiv result")

def _validate_inputs(evidence: Sequence[int], density: Sequence[int]) -> tuple[list[int], list[int]]:
    if isinstance(evidence, (str, bytes)) or not isinstance(evidence, (list, tuple)):
        raise TypeError("evidence must be a list or tuple of integers")
    if isinstance(density, (str, bytes)) or not isinstance(density, (list, tuple)):
        raise TypeError("density must be a list or tuple of integers")
    if len(evidence) != 6 or len(density) != 6:
        raise ValueError("SPEC-004 requires exactly six evidence and six density values")
    ev = [_i64(v, label=f"evidence[{i}]") for i, v in enumerate(evidence)]
    den = [_i64(v, label=f"density[{i}]") for i, v in enumerate(density)]
    # Candidate input profile carries forward the documented nonnegative evidence
    # and density-in-[0,Q] checks. It deliberately does not invent a semantic
    # evidence cap below signed i64; such a cap needs an explicit ratified rule.
    for i, value in enumerate(ev):
        if value < 0:
            raise ValueError(f"evidence[{i}] must be nonnegative")
    for i, value in enumerate(den):
        if value < 0 or value > Q:
            raise ValueError(f"density[{i}] must be within [0,Q]")
    return ev, den

def derive_state(evidence: Sequence[int], density: Sequence[int], transform: str) -> list[int]:
    ev, den = _validate_inputs(evidence, density)
    if not isinstance(transform, str):
        raise TypeError("transform must be a string")
    state: list[int] = []
    for d, e in zip(den, ev):
        state.extend((d, e))
    if transform == "none":
        return state
    prefix = "rotate_d1_"
    if not transform.startswith(prefix):
        raise ValueError("unsupported transform")
    angle_text = transform[len(prefix):]
    if not angle_text or any(ch not in "0123456789" for ch in angle_text):
        raise ValueError("invalid transform angle")
    angle = int(angle_text)
    if str(angle) != angle_text:
        raise ValueError("transform angle is not canonically encoded")
    if angle not in ROTATION_TABLE:
        raise ValueError("unsupported transform angle")
    c, s = ROTATION_TABLE[angle]
    real, imag = state[2], state[3]
    real_num = _i128(c * real - s * imag, label="rotation real numerator")
    imag_num = _i128(s * real + c * imag, label="rotation imag numerator")
    state[2] = _i64(qdiv(real_num, Q), label="rotated density")
    state[3] = _i64(qdiv(imag_num, Q), label="rotated evidence")
    return state

def compute_u_metric(evidence: Sequence[int], density: Sequence[int], state: Sequence[int]) -> dict[str, int]:
    ev, den = _validate_inputs(evidence, density)
    if isinstance(state, (str, bytes)) or not isinstance(state, (list, tuple)):
        raise TypeError("state must be a list or tuple of integers")
    if len(state) != 12:
        raise ValueError("SPEC-004 state must contain exactly twelve integers")
    st = [_i64(v, label=f"state[{i}]") for i, v in enumerate(state)]
    vh = 0
    for e, d in zip(ev, den):
        vh = _i128(vh + max(Q, abs(e)) + d, label="V_h")
    if vh <= 0:
        raise ValueError("V_h must be positive")
    ah = qdiv(vh, 100)
    delta = 0
    for i in range(6):
        delta = _i128(delta + abs(st[2*i] - Q) + abs(st[2*i+1] - Q), label="Delta")
    c = qdiv(_i128(delta * Q, label="Delta * Q"), vh)
    adjusted_vh = _i128(vh + ah, label="V_h + A_h")
    raw = qdiv(_i128(c * adjusted_vh, label="C * (V_h + A_h)"), vh)
    u = max(0, min(Q, raw))
    return {"V_h": vh, "A_h": ah, "delta": delta, "C": c, "u_raw": raw, "u_metric": u}

def decision_from_u(u_metric: int) -> str:
    u = _integer(u_metric, label="u_metric")
    if u < 0 or u > Q:
        raise ValueError("u_metric must be clamped to [0,Q]")
    if u <= T_PROCEED:
        return "PROCEED"
    if u <= T_REVIEW:
        return "REVIEW"
    return "BLOCK"

def canonical_audit_bytes(record: dict[str, Any]) -> bytes:
    """Candidate compact-JSON profile; floats and unreviewed fields are forbidden."""
    if not isinstance(record, dict):
        raise TypeError("audit record must be an object")
    field_order = [
        "spec_version", "prev_state_hash", "timestamp", "input_bundle",
        "operator", "operator_version", "applied_transforms", "result_state",
        "u_metric", "decision",
    ]
    if list(record.keys()) != field_order:
        raise ValueError("audit record fields/order do not match candidate v0.3.1 profile")
    bundle = record["input_bundle"]
    if not isinstance(bundle, dict) or list(bundle.keys()) != ["evidence", "density", "source_id"]:
        raise ValueError("input_bundle fields/order do not match candidate v0.3.1 profile")
    for key in ("spec_version", "prev_state_hash", "timestamp", "operator", "operator_version", "decision"):
        if not isinstance(record[key], str):
            raise TypeError(f"{key} must be a string")
    if not isinstance(bundle["source_id"], str):
        raise TypeError("input_bundle.source_id must be a string")
    if not isinstance(record["applied_transforms"], list) or not all(isinstance(x, str) for x in record["applied_transforms"]):
        raise TypeError("applied_transforms must be a list of strings")
    for key in ("evidence", "density"):
        values = bundle[key]
        if not isinstance(values, list) or any(type(x) is not int for x in values):
            raise TypeError(f"input_bundle.{key} must be a list of integers")
    if not isinstance(record["result_state"], list) or any(type(x) is not int for x in record["result_state"]):
        raise TypeError("result_state must be a list of integers")
    _integer(record["u_metric"], label="u_metric")
    def reject_floats(value: Any, path: str = "$") -> None:
        if type(value) is float:
            raise TypeError(f"floating-point value forbidden in audit domain at {path}")
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise TypeError(f"non-string key at {path}")
                reject_floats(item, f"{path}.{key}")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                reject_floats(item, f"{path}[{i}]")
    reject_floats(record)
    return json.dumps(record, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

#!/usr/bin/env python3
"""Candidate SPEC-004 validator for AETHEL Grid TV-001..TV-007.

This validator intentionally does NOT establish canonical conformance. It anchors
the candidate expected-result preimages in code and exercises the repository's
currently documented bootstrap state semantics.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
VECTOR_DIR = ROOT / "vectors"
SPECIFICATION_ID = "SPEC-004"
SPECIFICATION_VERSION = "candidate-0.1"

ANCHORS = {
    "TV-001": "b272b066f563be014f78ee1ca78e584eecc81dbfaf9656947ab2640e9d55376f",
    "TV-002": "9324fe4fabf585e9529220c6766b5246a47b31c1ef970e8016469739791a38c1",
    "TV-003": "0fa9e031e64eb704b7535295e833cb1740a004a42a8124538caa2caf5eae03e0",
    "TV-004": "f73ed4453bb9a361d79921182c5975f0c029c9fa0fcfb0a90724de3c049082d1",
    "TV-005": "38ce620e490b669ccf9c2a5276d0d4193a96903bffe37e8dc168503b444d3268",
    "TV-006": "e09a8224d7dd7274d66d4f325392ae04b4d3606f95c9291bd665f99ffe569db5",
    "TV-007": "dcdb0a9b238047513f7713c67842e8f625167ed13e9d4c6e2d33c903af61b998",
}


def canonical_json_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 JSON; non-finite numeric values are forbidden."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def state_sha256(state: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(state)).hexdigest()


def reject_non_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NON_FINITE_METRIC")
    if isinstance(value, dict):
        for item in value.values():
            reject_non_finite(item)
    elif isinstance(value, list):
        for item in value:
            reject_non_finite(item)


def topo_order(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(event["id"]): event for event in events}
    indegree = {event_id: 0 for event_id in by_id}
    children: dict[str, list[str]] = {event_id: [] for event_id in by_id}

    for event_id, event in by_id.items():
        for parent in event.get("parents", []):
            parent_id = str(parent)
            if parent_id not in by_id:
                raise ValueError(f"MISSING_PARENT:{parent_id}")
            indegree[event_id] += 1
            children[parent_id].append(event_id)

    ready = sorted(event_id for event_id, degree in indegree.items() if degree == 0)
    ordered: list[str] = []

    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready.sort()

    if len(ordered) != len(by_id):
        raise ValueError("CYCLE_DETECTED")

    return [by_id[event_id] for event_id in ordered]


def fold(events: list[dict[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for event in topo_order(events):
        patch = event.get("state", {})
        if not isinstance(patch, dict):
            raise ValueError("EVENT_STATE_MUST_BE_OBJECT")
        state.update(patch)
    return state


def evaluate(vector: dict[str, Any]) -> dict[str, Any]:
    tid = vector["test_id"]
    source = vector["input"]

    if tid == "TV-001":
        state = fold(source["events"])
        return {
            "status": "PASS",
            "state_sha256": state_sha256(state),
            "reason_code": "EMPTY_STATE",
        }

    if tid == "TV-002":
        events = source["events"]
        ordered = topo_order(events)
        state = fold(events)
        return {
            "status": "PASS",
            "state_sha256": state_sha256(state),
            "ordered_event_ids": [str(event["id"]) for event in ordered],
        }

    if tid == "TV-003":
        active = {str(peer) for peer in source["active_peers"]}
        approvals = {str(peer) for peer in source["approving_peers"]}
        threshold = float(source["quorum_threshold"])
        if not 0.0 < threshold <= 1.0:
            raise ValueError("INVALID_QUORUM_THRESHOLD")
        required = max(1, math.ceil(len(active) * threshold))
        valid_approvals = approvals.intersection(active)
        if len(valid_approvals) < required:
            raise ValueError("INSUFFICIENT_QUORUM")
        return {
            "status": "PASS",
            "required_quorum": required,
            "valid_approvals": len(valid_approvals),
            "active_peers": len(active),
        }

    if tid == "TV-004":
        if float(source["blast_radius"]) > float(source["max_blast_radius"]):
            return {"status": "REJECT", "reason_code": "BLAST_RADIUS_EXCEEDED"}
        raise ValueError("VECTOR_NOT_REJECTED")

    if tid == "TV-005":
        metrics = source["metrics"]
        reject_non_finite(metrics)
        for value in metrics.values():
            if isinstance(value, str) and value.strip().lower() in {"nan", "infinity", "+infinity", "-infinity"}:
                return {"status": "REJECT", "reason_code": "NON_FINITE_METRIC"}
        raise ValueError("VECTOR_NOT_REJECTED")

    if tid == "TV-006":
        size = int(source["payload_size_bytes"])
        limit = int(source["max_payload_bytes"])
        over = int(source["over_limit_size_bytes"])
        if size != limit:
            raise ValueError("BOUNDARY_ACCEPTANCE_FAILURE")
        if over <= limit:
            raise ValueError("OVER_LIMIT_CASE_INVALID")
        return {
            "status": "PASS",
            "accepted_bytes": size,
            "over_limit_status": "REJECT",
        }

    if tid == "TV-007":
        ordered = topo_order(source["events"])
        state = fold(source["events"])
        return {
            "status": "PASS",
            "ordered_event_ids": [str(event["id"]) for event in ordered],
            "state_sha256": state_sha256(state),
        }

    raise ValueError(f"UNKNOWN_VECTOR:{tid}")


def load_vector(test_id: str) -> dict[str, Any]:
    path = VECTOR_DIR / f"{test_id}.json"
    with path.open("r", encoding="utf-8") as handle:
        vector = json.load(handle)
    if vector.get("specification_id") != SPECIFICATION_ID:
        raise ValueError(f"{test_id}: SPECIFICATION_ID_MISMATCH")
    if vector.get("specification_version") != SPECIFICATION_VERSION:
        raise ValueError(f"{test_id}: SPECIFICATION_VERSION_MISMATCH")
    if vector.get("test_id") != test_id:
        raise ValueError(f"{test_id}: TEST_ID_MISMATCH")
    if vector.get("status") != "CANDIDATE_NONCANONICAL":
        raise ValueError(f"{test_id}: INVALID_CANONICALITY_STATUS")
    return vector


def validate() -> tuple[bool, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []

    for number in range(1, 8):
        test_id = f"TV-{number:03d}"
        try:
            vector = load_vector(test_id)
            expected = vector["expected"]
            observed = evaluate(vector)

            anchor = hashlib.sha256(canonical_json_bytes(expected)).hexdigest()
            if anchor != ANCHORS[test_id]:
                raise ValueError("EXPECTED_RESULT_ANCHOR_MISMATCH")
            if observed != expected:
                raise ValueError("OBSERVED_RESULT_MISMATCH")

            results.append({"test_id": test_id, "status": "PASS"})
        except Exception as exc:
            results.append(
                {"test_id": test_id, "status": "FAIL", "reason": str(exc)}
            )

    return all(item["status"] == "PASS" for item in results), results


def main() -> int:
    ok, results = validate()
    print(
        json.dumps(
            {
                "specification_id": SPECIFICATION_ID,
                "specification_version": SPECIFICATION_VERSION,
                "canonicality": "CANDIDATE_NONCANONICAL",
                "validator_id": "AETHEL-SPEC-004-CANDIDATE",
                "validator_version": "0.1.0",
                "result": "PASS" if ok else "FAIL",
                "vectors": results,
                "canonical_promotion": "BLOCKED_PENDING_EXTERNAL_RATIFICATION",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

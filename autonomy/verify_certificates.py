#!/usr/bin/env python3
"""
Verify a CAIOS certificate JSONL chain.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from autonomy.caios_runtime import DecisionCertificate, Evidence, digest


def certificate_from_dict(item: dict[str, Any]) -> DecisionCertificate:
    return DecisionCertificate(
        cycle=int(item["cycle"]),
        selected_action=item.get("selected_action"),
        decision=str(item["decision"]),
        score=float(item["score"]),
        gaps_before={str(k): float(v) for k, v in item.get("gaps_before", {}).items()},
        evidence=tuple(Evidence(**entry) for entry in item.get("evidence", [])),
        reasons=tuple(str(v) for v in item.get("reasons", [])),
        action_fingerprint=item.get("action_fingerprint"),
        previous_certificate_digest=item.get("previous_certificate_digest"),
        elapsed_ms=int(item.get("elapsed_ms", 0)),
        observation_digest=item.get("observation_digest"),
        council_digest=item.get("council_digest"),
        session_id=item.get("session_id"),
        session_anchor_hash=item.get("session_anchor_hash"),
        work_contract_digest=item.get("work_contract_digest"),
    )


def verify(path: Path) -> tuple[bool, list[str]]:
    errors = []
    previous = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            certificate = certificate_from_dict(item)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"line {line_number}: malformed certificate: {type(exc).__name__}")
            continue

        if item.get("proof_digest") != certificate.proof_digest:
            errors.append(f"line {line_number}: proof_digest mismatch")

        session_id = certificate.session_id
        anchor_hash = certificate.session_anchor_hash
        anchor_evidence = next(
            (
                entry for entry in item.get("evidence", [])
                if entry.get("kind") == "session-anchor"
            ),
            None,
        )
        if not session_id or not anchor_hash or not anchor_evidence:
            errors.append(f"line {line_number}: session anchor missing")
        elif anchor_evidence.get("digest") != anchor_hash:
            errors.append(f"line {line_number}: session anchor digest mismatch")

        if previous is not None and session_id != previous.get("session_id"):
            errors.append(f"line {line_number}: session_id changed within certificate chain")

        expected_previous = digest(previous) if previous is not None else None
        if item.get("previous_certificate_digest") != expected_previous:
            errors.append(f"line {line_number}: previous_certificate_digest mismatch")

        previous = item
    return not errors, errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="verify CAIOS certificate chain")
    parser.add_argument("path")
    args = parser.parse_args(argv)
    path = Path(args.path)
    ok, errors = verify(path)
    print(json.dumps({"status": "PASS" if ok else "FAIL", "errors": errors, "path": str(path)}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

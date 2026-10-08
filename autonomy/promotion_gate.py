#!/usr/bin/env python3
"""
CAIOS promotion gate.

Separates three states that must never be conflated:
- VERIFIED: the local autonomous evidence chain is internally valid.
- OPERATIONAL: the local runtime and deterministic tests are valid.
- CANONICAL: authoritative conformance and federation requirements are satisfied.

The default command emits HOLD rather than pretending canonical readiness.
Use --enforce in a promotion/deployment workflow to make HOLD fail the job.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from autonomy.evidence_bundle import build_bundle
from autonomy.verify_certificates import verify
from conformance.contract import inspect_contract


def evaluate(repo_root: Path) -> dict[str, Any]:
    contract = inspect_contract(repo_root)
    certificate_path = repo_root / "ops/caios/autonomy-certificates.jsonl"
    certificate_ok = certificate_path.is_file() and verify(certificate_path)[0]
    graph_ok = (repo_root / "ops/caios/proof-graph.json").is_file()

    bundle = build_bundle(repo_root)
    required_present = {
        entry["path"]: entry["status"] == "PRESENT"
        for entry in bundle["artifacts"]
    }

    operational = certificate_ok and graph_ok
    canonical = operational and contract.status == "PASS"

    decision = "PASS" if canonical else "HOLD"
    reason = (
        "canonical conformance and local proof evidence are satisfied"
        if canonical
        else "canonical readiness is not established; promotion remains held"
    )

    return {
        "schema": "caios-promotion-gate/v1",
        "decision": decision,
        "verified": bool(certificate_ok),
        "operational": bool(operational),
        "canonical": bool(canonical),
        "reason": reason,
        "conformance": contract.as_dict(),
        "artifacts": required_present,
        "bundle_digest": bundle["bundle_digest"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="evaluate CAIOS promotion readiness")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="ops/caios/promotion-decision.json")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    result = evaluate(root)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.enforce and result["decision"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate SPEC-005 candidate envelopes against JSON Schema and defensive invariants.

This validator does not verify Ed25519 signatures or certify a contract as trusted.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
SPEC_ID = "SPEC-005"
SPEC_VERSION = "candidate-0.1"
STATUS = "CANDIDATE_NONCANONICAL"
VECTOR_IDS = tuple(f"KC-{index:03d}" for index in range(1, 9))
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
DOMAIN_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
SIGNATURE_RE = re.compile(r"^[A-Za-z0-9+/]{86}==$")
RECOMMENDATIONS = {"INSPECT", "INVESTIGATE", "REQUEST_HUMAN_REVIEW"}

CONTRACT_REQUIRED = {
    "contract_id", "contract_version", "domain", "agent_id",
    "approved_model_digests", "approved_source_ids", "permitted_sensor_ids",
    "allowed_targets", "allowed_recommendations", "max_telemetry_age_seconds",
    "min_evidence_quality_micros", "valid_until_utc", "policy_id",
}
CONTRACT_OPTIONAL = {"prohibited_actions", "revoked"}
ENVELOPE_REQUIRED = {
    "contract", "signer_key_id", "issued_at_utc",
    "signature_algorithm", "signature_b64",
}


def canonical_json_bytes(value: Any) -> bytes:
    """Candidate profile only; not a claim of RFC 8785 conformance."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(IDENTIFIER_RE.fullmatch(value))


def has_duplicates(values: list[Any]) -> bool:
    # JSON-based keys make malformed nested JSON values safe to inspect too.
    keys = [json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for value in values]
    return len(keys) != len(set(keys))


def has_timezone(value: Any) -> bool:
    if not isinstance(value, str) or not DATETIME_RE.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _validate_unique_identifier_array(value: Any, field: str, errors: list[str], *, min_items: int = 1) -> None:
    if not isinstance(value, list):
        errors.append(f"{field}:not_array")
        return
    if len(value) < min_items:
        errors.append(f"{field}:too_few_items")
    if any(not is_identifier(item) for item in value):
        errors.append(f"{field}:invalid_identifier")
    if has_duplicates(value):
        errors.append(f"{field}:duplicates")


def validate_envelope(envelope: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(envelope, dict):
        return ["envelope:not_object"]
    if set(envelope) != ENVELOPE_REQUIRED:
        missing = sorted(ENVELOPE_REQUIRED - set(envelope))
        extra = sorted(set(envelope) - ENVELOPE_REQUIRED)
        if missing:
            errors.append("envelope:missing:" + ",".join(missing))
        if extra:
            errors.append("envelope:unknown:" + ",".join(extra))

    if not is_identifier(envelope.get("signer_key_id")):
        errors.append("signer_key_id:invalid_identifier")
    if not has_timezone(envelope.get("issued_at_utc")):
        errors.append("issued_at_utc:timezone_required")
    if envelope.get("signature_algorithm") != "Ed25519":
        errors.append("signature_algorithm:unsupported")
    signature_b64 = envelope.get("signature_b64")
    if not isinstance(signature_b64, str) or not SIGNATURE_RE.fullmatch(signature_b64):
        errors.append("signature_b64:invalid_format")
    else:
        try:
            decoded = base64.b64decode(signature_b64, validate=True)
            if len(decoded) != 64 or base64.b64encode(decoded).decode("ascii") != signature_b64:
                errors.append("signature_b64:invalid_ed25519_length_or_encoding")
        except (binascii.Error, ValueError):
            errors.append("signature_b64:invalid_base64")

    contract = envelope.get("contract")
    if not isinstance(contract, dict):
        errors.append("contract:not_object")
        return errors

    missing = sorted(CONTRACT_REQUIRED - set(contract))
    extra = sorted(set(contract) - CONTRACT_REQUIRED - CONTRACT_OPTIONAL)
    if missing:
        errors.append("contract:missing:" + ",".join(missing))
    if extra:
        errors.append("contract:unknown:" + ",".join(extra))

    for field in ("contract_id", "agent_id", "policy_id"):
        if not is_identifier(contract.get(field)):
            errors.append(f"{field}:invalid_identifier")
    version = contract.get("contract_version")
    if not isinstance(version, str) or not (1 <= len(version) <= 64):
        errors.append("contract_version:invalid_length")
    if not isinstance(contract.get("domain"), str) or not DOMAIN_RE.fullmatch(contract["domain"]):
        errors.append("domain:invalid_format")

    for field in ("approved_model_digests",):
        value = contract.get(field)
        if not isinstance(value, list):
            errors.append(f"{field}:not_array")
            continue
        if len(value) < 1:
            errors.append(f"{field}:too_few_items")
        if any(not isinstance(item, str) or not DIGEST_RE.fullmatch(item) for item in value):
            errors.append(f"{field}:invalid_digest")
        if has_duplicates(value):
            errors.append(f"{field}:duplicates")

    for field in ("approved_source_ids", "permitted_sensor_ids", "allowed_targets"):
        _validate_unique_identifier_array(contract.get(field), field, errors)

    recommendations = contract.get("allowed_recommendations")
    if not isinstance(recommendations, list):
        errors.append("allowed_recommendations:not_array")
    else:
        if len(recommendations) < 1:
            errors.append("allowed_recommendations:too_few_items")
        if any(not isinstance(item, str) or item not in RECOMMENDATIONS for item in recommendations):
            errors.append("allowed_recommendations:unsupported_value")
        if has_duplicates(recommendations):
            errors.append("allowed_recommendations:duplicates")

    prohibited = contract.get("prohibited_actions", [])
    if not isinstance(prohibited, list) or any(not isinstance(item, str) for item in prohibited):
        errors.append("prohibited_actions:invalid_array")
    elif has_duplicates(prohibited):
        errors.append("prohibited_actions:duplicates")

    max_age = contract.get("max_telemetry_age_seconds")
    if isinstance(max_age, bool) or not isinstance(max_age, int) or not (1 <= max_age <= 31536000):
        errors.append("max_telemetry_age_seconds:out_of_range")
    quality = contract.get("min_evidence_quality_micros")
    if isinstance(quality, bool) or not isinstance(quality, int) or not (0 <= quality <= 1000000):
        errors.append("min_evidence_quality_micros:out_of_range")
    if not has_timezone(contract.get("valid_until_utc")):
        errors.append("valid_until_utc:timezone_required")
    if "revoked" in contract and not isinstance(contract["revoked"], bool):
        errors.append("revoked:not_boolean")

    return sorted(set(errors))


def validate_vector(path: Path, schema_validator: Draft202012Validator) -> tuple[bool, list[str], dict[str, Any]]:
    try:
        vector = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"vector:read_error:{type(exc).__name__}"], {}

    errors: list[str] = []
    if not isinstance(vector, dict):
        return False, ["vector:not_object"], {}
    if vector.get("specification_id") != SPEC_ID:
        errors.append("vector:wrong_specification_id")
    if vector.get("specification_version") != SPEC_VERSION:
        errors.append("vector:wrong_specification_version")
    if vector.get("status") != STATUS:
        errors.append("vector:wrong_status")
    case_id = vector.get("case_id")
    if not isinstance(case_id, str) or not re.fullmatch(r"KC-00[1-8]", case_id):
        errors.append("vector:invalid_case_id")
    expected = vector.get("expected")
    if not isinstance(expected, dict) or not isinstance(expected.get("schema_valid"), bool):
        errors.append("vector:missing_schema_expectation")
        expected_valid = None
    else:
        expected_valid = expected["schema_valid"]
    if not isinstance(expected, dict) or expected.get("cryptographic_verification") != "NOT_EVALUATED":
        errors.append("vector:must_not_claim_crypto_verification")

    envelope = vector.get("envelope")
    envelope_errors = validate_envelope(envelope)
    manual_valid = len(envelope_errors) == 0
    json_schema_errors = sorted(
        f"{error.json_path or '


def main() -> int:
    schema_path = ROOT / "SPEC-005.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL schema_read:{type(exc).__name__}")
        return 2
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        print("FAIL schema_draft")
        return 2
    if schema.get("$id") != "https://aethel.example/specs/SPEC-005/candidate-0.1/schema.json":
        print("FAIL schema_id")
        return 2
    try:
        Draft202012Validator.check_schema(schema)
        schema_validator = Draft202012Validator(schema, format_checker=FormatChecker())
    except Exception as exc:
        print(f"FAIL schema_invalid:{type(exc).__name__}")
        return 2

    failures = 0
    seen: set[str] = set()
    for case_id in VECTOR_IDS:
        path = ROOT / "vectors" / f"{case_id}.json"
        ok, errors, evidence = validate_vector(path, schema_validator)
        if evidence.get("case_id") != case_id:
            ok = False
            errors = sorted(set(errors + [f"expected_case_id:{case_id}"]))
        if evidence.get("case_id"):
            seen.add(evidence["case_id"])
        label = "PASS" if ok else "FAIL"
        print(f"{label} {case_id} " + (",".join(errors) if errors else "schema_expectation_matched"))
        if not ok:
            failures += 1

    result = {
        "spec_id": SPEC_ID,
        "status": STATUS,
        "schema_sha256": sha256_hex(canonical_json_bytes(schema)),
        "vector_count": len(VECTOR_IDS),
        "failure_count": failures,
        "missing_vectors": sorted(set(VECTOR_IDS) - seen),
        "canonical_promotion": "BLOCKED_PENDING_EXTERNAL_RATIFICATION",
        "json_schema_cross_validation": "PERFORMED",
        "cryptographic_verification": "NOT_PERFORMED_BY_THIS_VALIDATOR",
    }
    print(json.dumps(result, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
}:{error.validator}"
        for error in schema_validator.iter_errors(envelope)
    )
    json_schema_valid = len(json_schema_errors) == 0
    if manual_valid != json_schema_valid:
        errors.append("validator_drift:manual_vs_json_schema")
    if expected_valid is not None and manual_valid != expected_valid:
        details = ",".join(envelope_errors) or "no_manual_errors"
        errors.append("vector:expected_manual_valid_mismatch:" + details)
    if expected_valid is not None and json_schema_valid != expected_valid:
        details = ",".join(json_schema_errors) or "no_json_schema_errors"
        errors.append("vector:expected_json_schema_valid_mismatch:" + details)
    if expected_valid is False and manual_valid:
        errors.append("vector:negative_case_did_not_fail_manual_validation")
    if expected_valid is False and json_schema_valid:
        errors.append("vector:negative_case_did_not_fail_json_schema_validation")
    return not errors, sorted(set(errors)), {
        "case_id": case_id,
        "manual_validator_valid": manual_valid,
        "manual_validator_errors": envelope_errors,
        "json_schema_valid": json_schema_valid,
        "json_schema_errors": json_schema_errors,
        "envelope_sha256": sha256_hex(canonical_json_bytes(envelope)),
    }


def main() -> int:
    schema_path = ROOT / "SPEC-005.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL schema_read:{type(exc).__name__}")
        return 2
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        print("FAIL schema_draft")
        return 2
    if schema.get("$id") != "https://aethel.example/specs/SPEC-005/candidate-0.1/schema.json":
        print("FAIL schema_id")
        return 2

    failures = 0
    seen: set[str] = set()
    for case_id in VECTOR_IDS:
        path = ROOT / "vectors" / f"{case_id}.json"
        ok, errors, evidence = validate_vector(path)
        if evidence.get("case_id") != case_id:
            ok = False
            errors = sorted(set(errors + [f"expected_case_id:{case_id}"]))
        if evidence.get("case_id"):
            seen.add(evidence["case_id"])
        label = "PASS" if ok else "FAIL"
        print(f"{label} {case_id} " + (",".join(errors) if errors else "schema_expectation_matched"))
        if not ok:
            failures += 1

    result = {
        "spec_id": SPEC_ID,
        "status": STATUS,
        "schema_sha256": sha256_hex(canonical_json_bytes(schema)),
        "vector_count": len(VECTOR_IDS),
        "failure_count": failures,
        "missing_vectors": sorted(set(VECTOR_IDS) - seen),
        "canonical_promotion": "BLOCKED_PENDING_EXTERNAL_RATIFICATION",
        "cryptographic_verification": "NOT_PERFORMED_BY_THIS_VALIDATOR",
    }
    print(json.dumps(result, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

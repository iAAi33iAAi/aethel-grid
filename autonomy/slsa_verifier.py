#!/usr/bin/env python3
"""
CAIOS in-toto/SLSA Statement verifier.

This validates statement structure and subject digests locally. Signature and
transparency verification remain the responsibility of Sigstore/Cosign or the
configured attestation service.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


IN_TOTO_STATEMENT = "https://in-toto.io/Statement/v1"
SLSA_PROVENANCE = "https://slsa.dev/provenance/v1"


def verify_statement(
    statement: dict[str, Any],
    *,
    subject_paths: dict[str, Path] | None = None,
) -> tuple[bool, list[str]]:
    errors = []
    if statement.get("_type") != IN_TOTO_STATEMENT:
        errors.append("statement-type-mismatch")
    if statement.get("predicateType") != SLSA_PROVENANCE:
        errors.append("predicate-type-mismatch")
    subjects = statement.get("subject")
    if not isinstance(subjects, list) or not subjects:
        errors.append("subject-missing")

    for subject in subjects if isinstance(subjects, list) else []:
        if not isinstance(subject, dict):
            errors.append("subject-not-object")
            continue
        name = str(subject.get("name", ""))
        digest_set = subject.get("digest")
        if not name or not isinstance(digest_set, dict):
            errors.append("subject-digest-missing")
            continue
        sha256 = digest_set.get("sha256")
        if sha256 is not None:
            if not isinstance(sha256, str) or len(sha256) != 64:
                errors.append(f"subject-sha256-invalid:{name}")
            elif subject_paths and name in subject_paths:
                h = hashlib.sha256(subject_paths[name].read_bytes()).hexdigest()
                if h != sha256:
                    errors.append(f"subject-sha256-mismatch:{name}")

    predicate = statement.get("predicate")
    if not isinstance(predicate, dict):
        errors.append("predicate-missing")
    else:
        build_definition = predicate.get("buildDefinition")
        run_details = predicate.get("runDetails")
        if not isinstance(build_definition, dict):
            errors.append("buildDefinition-missing")
        if not isinstance(run_details, dict):
            errors.append("runDetails-missing")

    return not errors, errors


def verify_file(path: Path, subject_paths: dict[str, Path] | None = None) -> tuple[bool, list[str]]:
    try:
        statement = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"statement-read-error:{type(exc).__name__}"]
    if not isinstance(statement, dict):
        return False, ["statement-not-object"]
    return verify_statement(statement, subject_paths=subject_paths)

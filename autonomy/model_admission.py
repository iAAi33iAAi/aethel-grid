#!/usr/bin/env python3
"""
CAIOS model admission.

Model identity is independent from agent identity. A registered agent may not
smuggle an unregistered model into the autonomous path.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelProfile:
    model_id: str
    model_class: str
    software_license: str
    weight_license: str
    service_terms_status: str
    redistribution: str
    production: str


class ModelRegistry:
    def __init__(self, repo_root: Path, path: str = "autonomy/model_registry.json") -> None:
        raw = json.loads((repo_root / path).read_text(encoding="utf-8"))
        self.policy = dict(raw.get("policy", {}))
        self.models = {
            item["model_id"]: ModelProfile(
                model_id=str(item["model_id"]),
                model_class=str(item["class"]),
                software_license=str(item["software_license"]),
                weight_license=str(item["weight_license"]),
                service_terms_status=str(item["service_terms_status"]),
                redistribution=str(item["redistribution"]),
                production=str(item["production"]),
            )
            for item in raw.get("models", [])
        }

    def get(self, model_id: str) -> ModelProfile | None:
        return self.models.get(model_id)

    def admit(self, model_id: str) -> tuple[bool, list[str]]:
        profile = self.get(model_id)
        if profile is None:
            return False, ["model-id-not-registered"]

        reasons = []
        if self.policy.get("weight_license_required", True) and not profile.weight_license:
            reasons.append("weight-license-missing")
        if profile.model_class == "hosted-service" and self.policy.get("service_terms_required", True):
            if profile.service_terms_status in {"UNKNOWN", "MISSING", "REQUIRED_OPERATOR_RECORD"}:
                reasons.append("service-terms-review-required")
        if profile.model_class == "local-code-model" and self.policy.get("source_commit_required_for_local_weights", True):
            reasons.append("local-model-source-pin-required")
        if "REQUIRES_MODEL_LICENSE_REVIEW" in profile.production:
            reasons.append("model-license-review-required")

        return not reasons, reasons

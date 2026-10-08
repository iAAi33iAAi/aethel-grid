#!/usr/bin/env python3
"""
CAIOS sovereign integration admission.

Unifies the separate software-license, model-license, protocol, tool, and
service-term checks into one auditable admission surface.

This is engineering metadata, not legal advice.

License: Apache-2.0
Copyright (c) 2026 iAAi33iAAi
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autonomy.evidence_bundle import digest


@dataclass(frozen=True)
class AdmissionProfile:
    integration_id: str
    category: str
    source_url: str
    license: str
    license_status: str
    version_or_revision: str | None
    provenance_ref: str | None
    service_terms_status: str | None
    production_status: str
    authority: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "integration_id": self.integration_id,
            "category": self.category,
            "source_url": self.source_url,
            "license": self.license,
            "license_status": self.license_status,
            "version_or_revision": self.version_or_revision,
            "provenance_ref": self.provenance_ref,
            "service_terms_status": self.service_terms_status,
            "production_status": self.production_status,
            "authority": self.authority,
        }


class SovereignAdmission:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def _load(self, relative: str, default: dict[str, Any]) -> dict[str, Any]:
        path = self.repo_root / relative
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {**default, "_invalid": relative}

    def evaluate(self) -> dict[str, Any]:
        tool_registry = self._load("integrations/caios_tool_registry.json", {"tools": []})
        protocol_registry = self._load("autonomy/protocol_registry.json", {"protocols": []})
        model_registry = self._load("autonomy/model_registry.json", {"models": []})

        profiles: list[AdmissionProfile] = []
        blockers: list[str] = []

        for item in tool_registry.get("tools", []):
            profiles.append(
                AdmissionProfile(
                    integration_id=f"tool:{item['id']}",
                    category="software",
                    source_url=str(item.get("source_url", "registry-local")),
                    license=str(item.get("license", "UNKNOWN")),
                    license_status="DECLARED",
                    version_or_revision=item.get("version"),
                    provenance_ref=item.get("provenance_ref"),
                    service_terms_status=None,
                    production_status="REQUIRES_VERSION_PIN" if not item.get("version") else "REVIEWABLE",
                    authority=str(item.get("authority", "unknown")),
                )
            )

        for item in protocol_registry.get("protocols", []):
            profiles.append(
                AdmissionProfile(
                    integration_id=f"protocol:{item['id']}",
                    category="protocol",
                    source_url=str(item.get("source_url", "")),
                    license=str(item.get("license", "UNKNOWN")),
                    license_status="DECLARED",
                    version_or_revision=str(item.get("latest_known_revision", "")),
                    provenance_ref=item.get("source_url"),
                    service_terms_status=None,
                    production_status="REVIEWABLE",
                    authority="transport-only",
                )
            )

        for item in model_registry.get("models", []):
            service_terms = item.get("service_terms_status")
            production = str(item.get("production", "REQUIRES_REVIEW"))
            if "REQUIRES" in production:
                production_status = "REQUIRES_REVIEW"
            else:
                production_status = production
            profiles.append(
                AdmissionProfile(
                    integration_id=f"model:{item['model_id']}",
                    category="model",
                    source_url=str(item.get("source_url", "registry-local")),
                    license=str(item.get("weight_license", item.get("software_license", "UNKNOWN"))),
                    license_status="DECLARED",
                    version_or_revision=item.get("revision"),
                    provenance_ref=item.get("provenance_ref"),
                    service_terms_status=service_terms,
                    production_status=production_status,
                    authority="proposal-input",
                )
            )

        for profile in profiles:
            if profile.license in {"UNKNOWN", ""}:
                blockers.append(f"{profile.integration_id}:license")
            if profile.category in {"software", "model"} and not profile.version_or_revision:
                blockers.append(f"{profile.integration_id}:version-or-revision")
            if profile.category == "model" and profile.service_terms_status in {
                "UNKNOWN", "MISSING", "REQUIRED_OPERATOR_RECORD"
            }:
                blockers.append(f"{profile.integration_id}:service-terms")

        material = {
            "schema": "caios-sovereign-admission/v1",
            "profiles": [profile.as_dict() for profile in sorted(profiles, key=lambda p: p.integration_id)],
            "blockers": sorted(set(blockers)),
            "note": "Metadata and policy gates only; final legal review remains external to the runtime.",
        }
        return {
            **material,
            "admission_digest": digest(material),
            "status": "HOLD" if blockers else "REVIEWABLE",
        }


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="build CAIOS sovereign integration admission report")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="ops/caios/sovereign-admission.json")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    result = SovereignAdmission(root).evaluate()
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from pathlib import Path
import json

from autonomy.model_admission import ModelRegistry


def _write_registry(tmp_path: Path, models):
    (tmp_path / "autonomy").mkdir()
    (tmp_path / "autonomy/model_registry.json").write_text(
        json.dumps({
            "policy": {
                "unknown_model": "REJECT",
                "service_terms_required": True,
                "weight_license_required": True,
                "source_commit_required_for_local_weights": True
            },
            "models": models
        }),
        encoding="utf-8",
    )


def test_unknown_model_is_rejected(tmp_path: Path):
    _write_registry(tmp_path, [])
    ok, reasons = ModelRegistry(tmp_path).admit("unknown")
    assert ok is False
    assert "model-id-not-registered" in reasons


def test_local_model_requires_revision_pin(tmp_path: Path):
    _write_registry(tmp_path, [{
        "model_id":"local-code",
        "class":"local-code-model",
        "software_license":"Apache-2.0",
        "weight_license":"Apache-2.0",
        "service_terms_status":"N/A_LOCAL",
        "redistribution":"ALLOWED",
        "production":"REQUIRES_EXACT_REVISION_PIN"
    }])
    ok, reasons = ModelRegistry(tmp_path).admit("local-code")
    assert ok is False
    assert "local-model-source-pin-required" in reasons


def test_reviewed_hosted_model_can_be_admitted(tmp_path: Path):
    _write_registry(tmp_path, [{
        "model_id":"hosted",
        "class":"hosted-service",
        "software_license":"N/A",
        "weight_license":"N/A",
        "service_terms_status":"REVIEWED",
        "redistribution":"N/A",
        "production":"ALLOWED_AFTER_REVIEW"
    }])
    ok, reasons = ModelRegistry(tmp_path).admit("hosted")
    assert ok is True
    assert reasons == []

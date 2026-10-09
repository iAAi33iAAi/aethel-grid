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
    assert "model-revision-missing" in reasons


def test_reviewed_hosted_model_can_be_admitted(tmp_path: Path):
    _write_registry(tmp_path, [{
        "model_id":"hosted",
        "class":"hosted-service",
        "software_license":"N/A",
        "weight_license":"N/A",
        "service_terms_status":"REVIEWED",
        "redistribution":"N/A",
        "production":"ALLOWED_AFTER_REVIEW",
        "terms_ref":"operator-reviewed-terms"
    }])
    ok, reasons = ModelRegistry(tmp_path).admit("hosted")
    assert ok is True
    assert reasons == []


def test_exact_revision_policy_requires_registry_anchored_revision(tmp_path: Path):
    _write_registry(tmp_path, [{
        "model_id":"pinned-model",
        "class":"local-code-model",
        "software_license":"Apache-2.0",
        "weight_license":"Apache-2.0",
        "service_terms_status":"N/A_LOCAL",
        "redistribution":"ALLOWED",
        "production":"REQUIRES_EXACT_REVISION_PIN"
    }])
    ok, reasons = ModelRegistry(tmp_path).admit(
        "pinned-model",
        model_revision="sha256:claimed-by-caller",
    )
    assert ok is False
    assert "registry-model-revision-not-pinned" in reasons


def test_exact_revision_policy_rejects_mismatch(tmp_path: Path):
    _write_registry(tmp_path, [{
        "model_id":"pinned-model",
        "class":"local-code-model",
        "software_license":"Apache-2.0",
        "weight_license":"Apache-2.0",
        "service_terms_status":"N/A_LOCAL",
        "redistribution":"ALLOWED",
        "production":"REQUIRES_EXACT_REVISION_PIN",
        "revision":"sha256:approved"
    }])
    ok, reasons = ModelRegistry(tmp_path).admit(
        "pinned-model",
        model_revision="sha256:other",
    )
    assert ok is False
    assert "model-revision-mismatch" in reasons


def test_exact_revision_policy_accepts_only_registry_match(tmp_path: Path):
    _write_registry(tmp_path, [{
        "model_id":"pinned-model",
        "class":"local-code-model",
        "software_license":"Apache-2.0",
        "weight_license":"Apache-2.0",
        "service_terms_status":"N/A_LOCAL",
        "redistribution":"ALLOWED",
        "production":"REQUIRES_EXACT_REVISION_PIN",
        "revision":"sha256:approved"
    }])
    ok, reasons = ModelRegistry(tmp_path).admit(
        "pinned-model",
        model_revision="sha256:approved",
    )
    assert ok is True
    assert reasons == []

from pathlib import Path
import json

from autonomy.sovereign_admission import SovereignAdmission


def test_admission_distinguishes_model_and_software(tmp_path: Path):
    (tmp_path / "autonomy").mkdir()
    (tmp_path / "integrations").mkdir()

    (tmp_path / "integrations/caios_tool_registry.json").write_text(
        json.dumps({
            "tools":[{
                "id":"pytest",
                "capability":"verification",
                "authority":"deterministic",
                "license":"MIT",
                "version":"8.4.2"
            }]
        }),
        encoding="utf-8",
    )
    (tmp_path / "autonomy/protocol_registry.json").write_text(
        json.dumps({
            "protocols":[{
                "id":"acp",
                "latest_known_revision":"1",
                "license":"Apache-2.0",
                "source_url":"https://example.invalid/acp",
                "status":"stable",
                "transport_role":"agent-client",
                "draft":False
            }]
        }),
        encoding="utf-8",
    )
    (tmp_path / "autonomy/model_registry.json").write_text(
        json.dumps({
            "models":[{
                "model_id":"m",
                "class":"hosted-service",
                "software_license":"N/A",
                "weight_license":"N/A",
                "service_terms_status":"REVIEWED",
                "redistribution":"N/A",
                "production":"ALLOWED_AFTER_REVIEW",
                "revision":"service-version",
                "terms_ref":"review-record"
            }]
        }),
        encoding="utf-8",
    )
    result = SovereignAdmission(tmp_path).evaluate()
    assert result["status"] == "REVIEWABLE"
    ids = {row["integration_id"] for row in result["profiles"]}
    assert {"tool:pytest","protocol:acp","model:m"} <= ids


def test_missing_revision_is_hold(tmp_path: Path):
    (tmp_path / "autonomy").mkdir()
    (tmp_path / "integrations").mkdir()
    (tmp_path / "autonomy/model_registry.json").write_text(
        json.dumps({"models":[{
            "model_id":"m",
            "class":"local-code-model",
            "software_license":"N/A",
            "weight_license":"Apache-2.0",
            "service_terms_status":"N/A_LOCAL",
            "redistribution":"ALLOWED",
            "production":"REQUIRES_REVIEW"
        }]}),
        encoding="utf-8",
    )
    (tmp_path / "autonomy/protocol_registry.json").write_text(json.dumps({"protocols":[]}), encoding="utf-8")
    (tmp_path / "integrations/caios_tool_registry.json").write_text(json.dumps({"tools":[]}), encoding="utf-8")
    result = SovereignAdmission(tmp_path).evaluate()
    assert result["status"] == "HOLD"
    assert "model:m:version-or-revision" in result["blockers"]

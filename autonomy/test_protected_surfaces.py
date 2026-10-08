from pathlib import Path
import json

from autonomy.caios_runtime import CandidateAction, ConstitutionalGate


def write_policy(tmp_path: Path):
    (tmp_path / "autonomy").mkdir()
    (tmp_path / "autonomy/protected_surfaces.json").write_text(
        json.dumps({
            "protected_globs": ["conformance/**", "autonomy/caios_runtime.py"]
        }),
        encoding="utf-8",
    )


def test_autonomous_patch_cannot_change_protected_surface(tmp_path: Path):
    write_policy(tmp_path)
    gate = ConstitutionalGate(tmp_path)
    action = CandidateAction(
        action_id="model-1-patch",
        kind="apply_patch",
        target=".",
        rationale="modify validator",
        expected_gain=0.7,
        risk=0.3,
        reversibility=1.0,
        resource_cost=0.2,
        evidence_gain=0.9,
        unified_diff="""diff --git a/conformance/canonical_contract.json b/conformance/canonical_contract.json
--- a/conformance/canonical_contract.json
+++ b/conformance/canonical_contract.json
@@ -1 +1 @@
-old
+new
""",
    )
    allowed, reasons = gate.validate(action)
    assert allowed is False
    assert "patch targets protected autonomous-control surface" in reasons


def test_application_patch_remains_eligible(tmp_path: Path):
    write_policy(tmp_path)
    gate = ConstitutionalGate(tmp_path)
    action = CandidateAction(
        action_id="model-1-patch",
        kind="apply_patch",
        target="src",
        rationale="improve application",
        expected_gain=0.7,
        risk=0.3,
        reversibility=1.0,
        resource_cost=0.2,
        evidence_gain=0.9,
        unified_diff="""diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-old
+new
""",
    )
    allowed, reasons = gate.validate(action)
    assert allowed is True

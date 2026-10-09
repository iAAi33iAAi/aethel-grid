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
    (tmp_path / "autonomy/authority_lattice.json").write_text(
        json.dumps({
            "schema": "caios-authority-lattice/v1",
            "principals": [{
                "principal_id": "caios",
                "authority": 30,
                "capabilities": ["observe", "propose", "evidence", "policy", "supervise"],
                "boundary": "repository-root-and-declared-federation",
            }],
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


def _patch_action(target: str = "src/app.py", path: str = "src/app.py") -> CandidateAction:
    return CandidateAction(
        action_id="safe-patch",
        kind="apply_patch",
        target=target,
        rationale="test protected-surface enforcement",
        expected_gain=0.5,
        risk=0.1,
        reversibility=1.0,
        resource_cost=0.1,
        evidence_gain=0.8,
        unified_diff=f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-old
+new
""",
    )


def test_mandatory_protected_surfaces_cannot_be_removed_by_configuration(tmp_path: Path):
    write_policy(tmp_path)
    policy_path = tmp_path / "autonomy" / "protected_surfaces.json"
    policy_path.write_text(
        json.dumps({"protected_globs": ["src/**"]}),
        encoding="utf-8",
    )

    gate = ConstitutionalGate(tmp_path)

    for path in (
        "conformance/canonical_contract.json",
        "autonomy/protected_surfaces.json",
    ):
        allowed, reasons = gate.validate(_patch_action(path=path))
        assert allowed is False, path
        assert "patch targets protected autonomous-control surface" in reasons, path

    assert gate.protected_policy_valid is True


def test_malformed_protected_surface_policies_block_all_autonomous_patches(tmp_path: Path):
    malformed_policies = [
        "{",
        "[]",
        "{}",
        json.dumps({"protected_globs": []}),
        json.dumps({"protected_globs": "conformance/**"}),
        json.dumps({"protected_globs": ["valid/**", 7]}),
    ]

    for index, serialized_policy in enumerate(malformed_policies):
        case_root = tmp_path / str(index)
        _seed = case_root / "autonomy"
        _seed.mkdir(parents=True)
        (_seed / "protected_surfaces.json").write_text(serialized_policy, encoding="utf-8")
        (_seed / "authority_lattice.json").write_text(
            json.dumps({
                "schema": "caios-authority-lattice/v1",
                "principals": [{
                    "principal_id": "caios",
                    "authority": 30,
                    "capabilities": ["observe", "propose", "policy", "supervise"],
                    "boundary": "test",
                }],
            }),
            encoding="utf-8",
        )

        gate = ConstitutionalGate(case_root)
        allowed, reasons = gate.validate(_patch_action())

        assert allowed is False
        assert gate.protected_policy_valid is False
        assert any("protected-surface-policy-unavailable" in reason for reason in reasons)


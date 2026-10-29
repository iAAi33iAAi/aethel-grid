from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops.agent_colony.model_review import (
    _load_evidence_report,
    _metadata_findings,
    _summarize_proposals,
    run_model_review,
    validate_model_review_config,
)


ROLES = (
    "protocol_analyst",
    "security_analyst",
    "devops_qa",
    "toolbox_architect",
)


class FakeProvider:
    def __init__(self, agent_ids):
        self.agent_ids = list(agent_ids)
        self.last_errors = []
        self.snapshot = None
        self.task_contexts = None

    def propose(self, snapshot, *, task_contexts=None):
        self.snapshot = snapshot
        self.task_contexts = task_contexts
        return [
            {
                "agent_id": agent_id,
                "finding_id": "AC-001",
                "kind": "review_finding",
                "target": "conformance/GATE_STATUS.json",
                "rationale": "Review the unresolved gate; api_key=NEVER_EMIT_THIS",
                "risk": 0.2,
                "unified_diff": "SHOULD_NOT_BE_RETURNED",
                "command": ["echo", "SHOULD_NOT_RUN"],
            }
            for agent_id in self.agent_ids
        ]


class ModelReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "autonomy").mkdir()
        (self.root / "ops" / "agent_colony").mkdir(parents=True)
        self.config_path = self.root / "autonomy" / "agent_endpoints.json"
        self.manifest_path = self.root / "ops" / "agent_colony" / "manifest.json"
        self.registry_path = self.root / "autonomy" / "provider_endpoint_registry.json"
        self.agent_ids = [f"agent-{role}" for role in ROLES]
        self._write_manifest_and_registry()
        self._write_config()

    def tearDown(self):
        self.temp.cleanup()

    def _write_manifest_and_registry(self):
        manifest = {
            "schema": "aethel-agent-colony/v1",
            "report_contract": {"severity_values": ["critical", "high", "medium", "low", "info"]},
            "agents": [
                {
                    "id": role,
                    "role": f"Review as {role}",
                    "stage": "S1",
                    "toolbox_id": f"tb-{role}",
                }
                for role in ROLES
            ],
            "toolboxes": [
                {
                    "id": f"tb-{role}",
                    "allow": ["read_specs"],
                    "deny": ["write_file", "push_branch", "merge_pr", "read_secret_values", "network_request"],
                }
                for role in ROLES
            ],
        }
        registry = {
            "schema": "caios-provider-endpoints/v1",
            "policy": {
                "unknown_endpoint": "REJECT",
                "exact_url_match": True,
                "exact_agent_model_protocol_match": True,
                "require_approval_ref": True,
            },
            "endpoints": [],
        }
        for index, role in enumerate(ROLES, start=1):
            slug = role.replace("_", "-")
            registry["endpoints"].append({
                "id": f"endpoint-{slug}",
                "endpoint_url": f"https://provider-{slug}.example.invalid/v1/chat/completions",
                "agent_id": f"agent-{role}",
                "agent_version": "1.0.0",
                "source_ref": f"https://github.com/example/repo/blob/{index:040d}/autonomy/caios_runtime.py",
                "protocol": "caios-openai-compatible-proposal-transport",
                "protocol_version": "1.0.0",
                "model_id": f"model-{slug}",
                "model_revision": f"revision-{slug}",
                "approval_ref": f"https://github.com/example/repo/pull/{index}",
                "api_key_env": f"CAIOS_{role.upper()}_API_KEY",
            })
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.registry_path.write_text(json.dumps(registry), encoding="utf-8")

    def _write_config(self):
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        agents = []
        for binding, role in zip(registry["endpoints"], ROLES):
            agents.append({
                "endpoint_id": binding["id"],
                "agent_id": binding["agent_id"],
                "role_id": role,
                "endpoint": binding["endpoint_url"],
                "model": binding["model_id"],
                "model_revision": binding["model_revision"],
                "protocol": binding["protocol"],
                "protocol_version": binding["protocol_version"],
                "agent_version": binding["agent_version"],
                "source_ref": binding["source_ref"],
                "api_key_env": binding["api_key_env"],
                "send_source_context": False,
            })
        self.config_path.write_text(
            json.dumps({"schema": "caios-agent-endpoints/v1", "agents": agents}),
            encoding="utf-8",
        )

    def test_missing_config_disables_model_calls(self):
        result = validate_model_review_config(
            self.root,
            config_path="autonomy/not-configured.json",
            manifest_path=self.manifest_path,
        )
        self.assertEqual(result["status"], "DISABLED")
        self.assertFalse(result["external_model_calls_attempted"])

    def test_preflight_validates_exact_pins_without_calling_provider(self):
        result = run_model_review(
            self.root,
            config_path=self.config_path,
            manifest_path=self.manifest_path,
        )
        self.assertEqual(result["status"], "READY_FOR_OPERATOR_REVIEW")
        self.assertEqual(result["provider_count"], 4)
        self.assertFalse(result["model_calls_attempted"])

    def test_rejects_endpoint_pin_mismatch(self):
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["agents"][0]["endpoint"] = "https://attacker.example.invalid/v1/chat/completions"
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "pin mismatch"):
            validate_model_review_config(
                self.root,
                config_path=self.config_path,
                manifest_path=self.manifest_path,
            )

    def test_rejects_source_context_for_model_review(self):
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["agents"][0]["send_source_context"] = True
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "send_source_context=false"):
            validate_model_review_config(
                self.root,
                config_path=self.config_path,
                manifest_path=self.manifest_path,
            )

    def test_requires_all_four_review_roles(self):
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["agents"] = config["agents"][:-1]
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exactly one provider"):
            validate_model_review_config(
                self.root,
                config_path=self.config_path,
                manifest_path=self.manifest_path,
            )

    def test_execution_requires_explicit_environment_kill_switch(self):
        fake = FakeProvider(self.agent_ids)
        with patch.dict(os.environ, {}, clear=True):
            result = run_model_review(
                self.root,
                config_path=self.config_path,
                manifest_path=self.manifest_path,
                findings=[],
                source_revision="a" * 40,
                execute=True,
                provider_loader=lambda _root, _path: fake,
            )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["model_calls_attempted"])
        self.assertIsNone(fake.snapshot)

    def test_fake_provider_receives_role_contexts_and_output_is_non_executable(self):
        findings = [{
            "id": "AC-001",
            "severity": "high",
            "title": "Fixture security finding",
            "evidence_path": "conformance/GATE_STATUS.json",
            "status": "open",
            "details": "SHOULD_NOT_BE_SENT",
        }]
        fake = FakeProvider(self.agent_ids)
        with patch.dict(os.environ, {"CAIOS_ENABLE_MODEL_COLLABORATION": "1"}, clear=True):
            result = run_model_review(
                self.root,
                config_path=self.config_path,
                manifest_path=self.manifest_path,
                findings=findings,
                source_revision="a" * 40,
                execute=True,
                provider_loader=lambda _root, _path: fake,
            )

        self.assertEqual(result["status"], "PROPOSALS_ONLY")
        self.assertTrue(result["model_calls_attempted"])
        self.assertFalse(result["code_changes_created"])
        self.assertFalse(result["tool_calls_executed"])
        self.assertEqual(set(fake.task_contexts), set(self.agent_ids))
        self.assertEqual(
            {task["role_id"] for task in fake.task_contexts.values()},
            set(ROLES),
        )
        self.assertTrue(all(task["egress_policy"]["tool_execution_authority"] is False for task in fake.task_contexts.values()))
        self.assertTrue(all(
            task["review_output_contract"]["finding_id_rule"].startswith("Must exactly match")
            for task in fake.task_contexts.values()
        ))
        self.assertTrue(all(
            task["review_output_contract"]["non_executable"] is True
            for task in fake.task_contexts.values()
        ))
        self.assertTrue(all("details" not in task["input_findings"][0] for task in fake.task_contexts.values()))
        self.assertNotIn("SHOULD_NOT_BE_SENT", json.dumps(fake.snapshot))
        self.assertNotIn("SHOULD_NOT_BE_RETURNED", json.dumps(result))
        self.assertNotIn("SHOULD_NOT_RUN", json.dumps(result))
        self.assertNotIn("NEVER_EMIT_THIS", json.dumps(result))
        self.assertEqual(len(result["proposals"]), 4)


    def test_model_proposals_must_reference_known_findings_and_cannot_set_evidence_path(self):
        clean_proposals, rejected_count, reasons = _summarize_proposals(
            [
                {
                    "agent_id": "agent-protocol",
                    "finding_id": "AC-001",
                    "kind": "review_finding",
                    "target": "injected/attacker-controlled/path.py",
                    "title": "Review known finding",
                    "rationale": "The finding should remain open until verified.",
                    "unified_diff": "must-not-escape",
                },
                {
                    "agent_id": "agent-security",
                    "finding_id": "AC-999",
                    "kind": "review_finding",
                    "title": "Invented finding reference",
                },
                {
                    "agent_id": "unregistered-agent",
                    "finding_id": "AC-001",
                    "kind": "review_finding",
                    "title": "Unregistered identity",
                },
            ],
            findings_by_id={
                "AC-001": {
                    "id": "AC-001",
                    "severity": "high",
                    "evidence_path": "conformance/GATE_STATUS.json",
                }
            },
            agent_roles={"agent-protocol": "protocol_analyst", "agent-security": "security_analyst"},
        )
        self.assertEqual(len(clean_proposals), 1)
        self.assertEqual(rejected_count, 2)
        self.assertEqual(reasons["unknown_or_missing_finding_id"], 1)
        self.assertEqual(reasons["unregistered_agent_identity"], 1)
        self.assertEqual(clean_proposals[0]["target"], "conformance/GATE_STATUS.json")
        self.assertEqual(clean_proposals[0]["role_id"], "protocol_analyst")
        self.assertNotIn("unified_diff", json.dumps(clean_proposals))
        self.assertNotIn("injected/attacker-controlled", json.dumps(clean_proposals))


    def test_evidence_intake_rejects_path_traversal_and_absolute_paths(self):
        base = {
            "id": "AC-001",
            "severity": "high",
            "title": "Fixture security finding",
            "evidence_path": "../secret.txt",
            "status": "open",
        }
        with self.assertRaisesRegex(ValueError, "unsafe evidence path"):
            _metadata_findings([base])
        base["evidence_path"] = "/etc/passwd"
        with self.assertRaisesRegex(ValueError, "unsafe evidence path"):
            _metadata_findings([base])

    def test_evidence_intake_rejects_duplicate_finding_ids(self):
        first = {
            "id": "AC-001",
            "severity": "high",
            "title": "First finding",
            "evidence_path": "conformance/GATE_STATUS.json",
            "status": "open",
            "details": "never-forward-this",
        }
        second = {
            "id": "AC-001",
            "severity": "critical",
            "title": "Conflicting duplicate",
            "evidence_path": "backend/stripe_bridge.py",
            "status": "open",
        }
        with self.assertRaisesRegex(ValueError, "duplicate finding ID"):
            _metadata_findings([first, second])


    def test_evidence_report_loader_requires_canonical_schema_and_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            report_path = Path(temp) / "report.json"
            report_path.write_text(json.dumps({
                "schema": "other-report/v1",
                "source_head_sha": "a" * 40,
                "findings": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema is not"):
                _load_evidence_report(report_path)

            report_path.write_text(json.dumps({
                "schema": "aethel-agent-colony-report/v1",
                "source_head_sha": "a" * 40,
                "findings": [],
            }), encoding="utf-8")
            revision, findings = _load_evidence_report(report_path)
            self.assertEqual(revision, "a" * 40)
            self.assertEqual(findings, [])

            report_path.write_text(json.dumps({
                "schema": "aethel-agent-colony-report/v1",
                "source_head_sha": "not-a-commit",
                "findings": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "commit SHA"):
                _load_evidence_report(report_path)


    def test_rejected_model_proposal_downgrades_status_to_partial(self):
        class OneInvalidProvider(FakeProvider):
            def propose(self, snapshot, *, task_contexts=None):
                rows = super().propose(snapshot, task_contexts=task_contexts)
                rows[0]["finding_id"] = "AC-DOES-NOT-EXIST"
                return rows

        findings = [{
            "id": "AC-001",
            "severity": "high",
            "title": "Fixture security finding",
            "evidence_path": "conformance/GATE_STATUS.json",
            "status": "open",
        }]
        fake = OneInvalidProvider(self.agent_ids)
        with patch.dict(os.environ, {"CAIOS_ENABLE_MODEL_COLLABORATION": "1"}, clear=True):
            result = run_model_review(
                self.root,
                config_path=self.config_path,
                manifest_path=self.manifest_path,
                findings=findings,
                source_revision="a" * 40,
                execute=True,
                provider_loader=lambda _root, _path: fake,
            )
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["rejected_proposal_count"], 1)
        self.assertEqual(result["rejected_proposal_reasons"]["unknown_or_missing_finding_id"], 1)
        self.assertEqual(result["release_decision"], "HOLD")
        self.assertFalse(result["code_changes_created"])


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from run_colony import run, validate_manifest
from toolbox_policy import ToolboxDispatcher, ToolboxPermissionError

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "ops" / "agent_colony" / "manifest.json"


class ColonyManifestTests(unittest.TestCase):
    def test_manifest_validates(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(validate_manifest(manifest), [])

    def test_mutation_capabilities_are_rejected(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest["policy"]["allow_merges"] = True
        self.assertTrue(any("allow_merges must be false" in e for e in validate_manifest(manifest)))

    def test_automated_toolboxes_must_deny_writes(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        toolbox = next(t for t in manifest["toolboxes"] if t["id"] == "tb_security_readonly")
        toolbox["deny"].remove("push_branch")
        self.assertTrue(any("missing mandatory deny rules" in e for e in validate_manifest(manifest)))

    def test_dependency_cycles_are_rejected(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        next(a for a in manifest["agents"] if a["id"] == "portfolio_cartographer")["depends_on"] = ["human_release_owner"]
        self.assertTrue(any("dependency cycle at" in e for e in validate_manifest(manifest)))



class ToolboxPolicyTests(unittest.TestCase):
    def _manifest(self):
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_allowlist_grants_declared_capability_and_denies_push(self):
        dispatcher = ToolboxDispatcher(self._manifest())
        dispatcher.authorize("security_analyst", "inspect_auth_code")
        with self.assertRaises(ToolboxPermissionError):
            dispatcher.authorize("security_analyst", "push_branch")
        audit = dispatcher.audit_log()
        self.assertEqual([row["decision"] for row in audit], ["ALLOW", "DENY"])

    def test_explicit_deny_overrides_allowlist(self):
        manifest = self._manifest()
        box = next(item for item in manifest["toolboxes"] if item["id"] == "tb_security_readonly")
        box["allow"].append("read_secret_values")
        dispatcher = ToolboxDispatcher(manifest)
        with self.assertRaises(ToolboxPermissionError):
            dispatcher.authorize("security_analyst", "read_secret_values")
        self.assertEqual(dispatcher.audit_log()[-1]["decision"], "DENY")

class ColonyRunnerTests(unittest.TestCase):
    def test_runner_reports_findings_without_secret_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "ops" / "agent_colony").mkdir(parents=True)
            (root / "ops" / "agent_colony" / "manifest.json").write_text(MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")
            (root / "conformance").mkdir()
            gate_status = {
                "gate_1": {"status": "BLOCKED"},
                "gate_3": {"status": "PARTIALLY_CLOSED"},
                "gate_4": {"status": "NOT_STARTED"},
                "gate_6": {"status": "BLOCKED"}
            }
            (root / "conformance" / "GATE_STATUS.json").write_text(json.dumps(gate_status), encoding="utf-8")
            (root / "autonomy").mkdir()
            (root / "autonomy" / "agent_router.py").write_text("# fixture: registry-based quorum planner\\n", encoding="utf-8")
            peer = root / "federated" / "openclaw-colony" / "backend"
            peer.mkdir(parents=True)
            (root / "federated" / "openclaw-colony" / ".env.windows").write_text("EXAMPLE_SECRET=never-print-this", encoding="utf-8")
            (peer / "biometric_routes.py").write_text('@router.post("/attest")\ndef attest():\n    return issue_attestation()\n', encoding="utf-8")
            (peer / "stripe_bridge.py").write_text('def _live_transfer():\n    stripe.Transfer.create()\n# ── Main entry point\n', encoding="utf-8")
            system = {"repositories": [
                {"id": "aethel-grid", "path": ".", "role": "root", "verification": ["python -m unittest"], "verification_scope": "unit tests"},
                {"id": "openclaw-colony", "path": "federated/openclaw-colony", "role": "colony", "verification": ["pytest"], "verification_scope": "narrow tests"}
            ]}
            sys_path = root / "federation" / "system_manifest.json"
            sys_path.parent.mkdir(parents=True)
            sys_path.write_text(json.dumps(system), encoding="utf-8")
            report = run(root, root / "ops" / "agent_colony" / "manifest.json", sys_path)
            self.assertEqual(report["portfolio"]["repositories_total"], 2)
            titles = {f["title"] for f in report["findings"]}
            self.assertIn("Workspace contains a non-example environment file (contents not inspected)", titles)
            self.assertIn("Biometric attestation lacks visible request-signature admission", titles)
            self.assertIn("Live Stripe transfer lacks complete signed-admission boundary", titles)
            self.assertIn("Model-backed collaboration is not configured in CAIOS", titles)
            self.assertFalse(report["architecture_review"]["provider_configuration"]["model_backed_agents_ready"])
            self.assertTrue(report["architecture_review"]["components"][0]["present"])
            rendered = json.dumps(report)
            self.assertNotIn("never-print-this", rendered)
            self.assertEqual(report["release_decision"], "HOLD")
            self.assertTrue(report["tool_execution_audit"])
            self.assertTrue(all(row["decision"] == "ALLOW" for row in report["tool_execution_audit"]))


    def test_security_probe_recognizes_signed_scanner_and_transfer_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "ops" / "agent_colony").mkdir(parents=True)
            (root / "ops" / "agent_colony" / "manifest.json").write_text(
                MANIFEST.read_text(encoding="utf-8"), encoding="utf-8"
            )
            (root / "conformance").mkdir()
            (root / "conformance" / "GATE_STATUS.json").write_text(
                json.dumps({
                    "gate_1": {"status": "BLOCKED"},
                    "gate_3": {"status": "PARTIALLY_CLOSED"},
                    "gate_4": {"status": "NOT_STARTED"},
                    "gate_6": {"status": "BLOCKED"},
                }),
                encoding="utf-8",
            )
            (root / "autonomy").mkdir()
            (root / "autonomy" / "agent_router.py").write_text(
                "# fixture: capability router\\n", encoding="utf-8"
            )
            peer = root / "federated" / "openclaw-colony" / "backend"
            peer.mkdir(parents=True)
            (peer / "biometric_routes.py").write_text(
                'from scanner_auth import verify_scanner_request\\n'
                '@router.post("/attest")\\n'
                'async def attest():\\n'
                '    timestamp = "X-Scanner-Timestamp"\\n'
                '    nonce = "X-Scanner-Nonce"\\n'
                '    signature = "X-Scanner-Signature"\\n'
                '    verify_scanner_request(db, timestamp=timestamp, nonce=nonce, signature=signature, body=signed_body)\\n',
                encoding="utf-8",
            )
            (peer / "stripe_bridge.py").write_text(
                'def _live_transfer(amount_cents, destination, task_id, label, idempotency_key, *, _permit=None):\\n'
                '    if _permit is not _TRANSFER_CALL_PERMIT: raise PermissionError("denied")\\n'
                '    stripe.Transfer.create(amount=amount_cents)\\n'
                '# ── Main entry point\\n'
                'def process_manna_payment(task_id, lineage_hash, *, admission=None, db=None):\\n'
                '    if os.environ.get("COLONY_LIVE_PAYMENTS_ENABLED", "").lower() != "true": return None\\n'
                '    ok, reason = verify_transfer_admission(db, admission, task_id=task_id, lineage_hash=lineage_hash, amount_cents=MANNA_CENTS)\\n'
                '    if not ok: return None\\n'
                '    community_id = _live_transfer(1, "acct", task_id, "community", "k1", _permit=_TRANSFER_CALL_PERMIT)\\n'
                '    crew_id = _live_transfer(1, "acct", task_id, "crew", "k2", _permit=_TRANSFER_CALL_PERMIT)\\n'
                '    architect_id = _live_transfer(1, "acct", task_id, "architect", "k3", _permit=_TRANSFER_CALL_PERMIT)\\n'
                '# ── Webhook verification\\n',
                encoding="utf-8",
            )
            (root / "federated" / "openclaw-colony" / "tests").mkdir(parents=True)
            (root / "federated" / "openclaw-colony" / "tests" / "test_payment_admission.py").write_text(
                "def test_raw_transfer_primitive_denies_direct_invocation(): pass\\n",
                encoding="utf-8",
            )
            system = {"repositories": [
                {"id": "aethel-grid", "path": ".", "role": "root",
                 "verification": ["python -m unittest"], "verification_scope": "unit tests"},
                {"id": "openclaw-colony", "path": "federated/openclaw-colony", "role": "colony",
                 "verification": ["pytest"], "verification_scope": "security tests"},
            ]}
            sys_path = root / "federation" / "system_manifest.json"
            sys_path.parent.mkdir(parents=True)
            sys_path.write_text(json.dumps(system), encoding="utf-8")

            report = run(root, root / "ops" / "agent_colony" / "manifest.json", sys_path)
            titles = {finding["title"] for finding in report["findings"]}
            self.assertNotIn(
                "Biometric attestation lacks visible request-signature admission", titles
            )
            self.assertNotIn(
                "Live Stripe transfer lacks complete signed-admission boundary", titles
            )
            self.assertEqual(report["release_decision"], "HOLD")


if __name__ == "__main__":
    unittest.main(verbosity=2)

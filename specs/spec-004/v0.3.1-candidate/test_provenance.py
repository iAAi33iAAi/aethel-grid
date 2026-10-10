"""Provenance and byte-integrity tests for the reconstructed candidate."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = json.loads((ROOT / "AMENDMENT_MANIFEST.json").read_text(encoding="utf-8"))

class ProvenanceTests(unittest.TestCase):
    def test_recovered_source_hashes_match_archived_manifest(self):
        for filename, key in [
            ("SPEC-004_v0.3.1_METRIC_LAW.md", "source_law_sha256"),
            ("spec004_v031_metric_law.py", "source_python_sha256"),
            ("archived_test_metric_law.py", "source_test_sha256"),
            ("golden_corpus_v0.3_RIGOR_DEPRECATED.md", "deprecated_v03_rigor_note_sha256"),
            ("WRITEBACK_STATUS.md", "writeback_status_sha256"),
        ]:
            with self.subTest(filename=filename):
                actual = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
                self.assertEqual(actual, MANIFEST[key])

    def test_reconstructed_corpus_file_hash_is_recorded(self):
        actual = hashlib.sha256((ROOT / "golden_corpus.json").read_bytes()).hexdigest()
        self.assertEqual(actual, MANIFEST["reconstructed_corpus_sha256"])

    def test_every_vector_preimage_and_digest_match(self):
        vectors = json.loads((ROOT / "golden_corpus.json").read_text(encoding="utf-8"))
        self.assertEqual(len(vectors), 4)
        for vector in vectors:
            with self.subTest(vector=vector["id"]):
                rendered = json.dumps(vector["audit_record"], separators=(",", ":"), ensure_ascii=False, allow_nan=False)
                self.assertEqual(rendered, vector["audit_preimage"])
                self.assertEqual(hashlib.sha256(rendered.encode("utf-8")).hexdigest(), vector["expected_sha256"])

if __name__ == "__main__":
    unittest.main(verbosity=2)

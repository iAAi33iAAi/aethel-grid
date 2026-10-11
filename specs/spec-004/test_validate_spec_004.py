"""Unit tests for candidate SPEC-004 vector parsing.

These tests protect the parser boundary only; they do not ratify SPEC-004.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_spec_004 as validator


class StrictVectorParsingTests(unittest.TestCase):
    def test_duplicate_json_object_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            validator.strict_json_loads('{"test_id":"TV-001","test_id":"TV-007"}')

    def test_nonstandard_numeric_constants_are_rejected(self):
        for raw in ('{"metric":NaN}', '{"metric":Infinity}', '{"metric":-Infinity}'):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, "non-standard JSON numeric constant"):
                    validator.strict_json_loads(raw)

    def test_vector_loader_uses_strict_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            vector_dir = Path(tmp)
            (vector_dir / "TV-001.json").write_text(
                '{"specification_id":"SPEC-004","specification_id":"ATTACKER"}',
                encoding="utf-8",
            )
            with patch.object(validator, "VECTOR_DIR", vector_dir):
                with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                    validator.load_vector("TV-001")

    def test_vector_document_must_be_an_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            vector_dir = Path(tmp)
            (vector_dir / "TV-001.json").write_text("[]", encoding="utf-8")
            with patch.object(validator, "VECTOR_DIR", vector_dir):
                with self.assertRaisesRegex(ValueError, "VECTOR_MUST_BE_OBJECT"):
                    validator.load_vector("TV-001")


if __name__ == "__main__":
    unittest.main(verbosity=2)

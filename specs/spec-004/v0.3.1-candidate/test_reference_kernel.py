"""Independent hardening checks for the v0.3.1 candidate."""
import hashlib
import json
import unittest
from pathlib import Path
import reference_kernel as law

ROOT = Path(__file__).resolve().parent

class V031CandidateTests(unittest.TestCase):
    def test_four_vectors_recompute_state_metric_decision_and_digest(self):
        vectors = json.loads((ROOT / "golden_corpus.json").read_text(encoding="utf-8"))
        self.assertEqual(len(vectors), 4)
        for vector in vectors:
            with self.subTest(vector=vector["id"]):
                record = vector["audit_record"]
                bundle = record["input_bundle"]
                state = law.derive_state(bundle["evidence"], bundle["density"], record["applied_transforms"][0])
                self.assertEqual(state, record["result_state"])
                metric = law.compute_u_metric(bundle["evidence"], bundle["density"], state)
                expected = dict(vector["derivation"])
                expected["u_metric"] = record["u_metric"]
                self.assertEqual(metric, expected)
                self.assertEqual(law.decision_from_u(metric["u_metric"]), record["decision"])
                encoded = law.canonical_audit_bytes(record)
                self.assertEqual(encoded.decode("utf-8"), vector["audit_preimage"])
                self.assertEqual(hashlib.sha256(encoded).hexdigest(), vector["expected_sha256"])

    def test_decision_boundaries(self):
        for value, result in {
            0:"PROCEED", 100000:"PROCEED", 100001:"REVIEW",
            900000:"REVIEW", 900001:"BLOCK", 1000000:"BLOCK",
        }.items():
            with self.subTest(value=value):
                self.assertEqual(law.decision_from_u(value), result)

    def test_signed_qdiv_truncates_toward_zero(self):
        for n,d,want in [(5,2,2),(-5,2,-2),(5,-2,-2),(-5,-2,2),(1,3,0),(-1,3,0)]:
            self.assertEqual(law.qdiv(n,d), want)

    def test_zero_division_and_integer_type_guards(self):
        with self.assertRaises(ZeroDivisionError):
            law.qdiv(1,0)
        for value in (True, 1.0, "1", None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    law.qdiv(value, 1)
                with self.assertRaises(TypeError):
                    law.decision_from_u(value)

    def test_i128_and_i64_limits(self):
        with self.assertRaises(OverflowError):
            law.qdiv(1 << 127, 1)
        with self.assertRaises(OverflowError):
            law.qdiv(law.I128_MIN, -1)
        with self.assertRaises(OverflowError):
            law.compute_u_metric([law.Q]*6, [law.Q]*6, [1 << 63] + [law.Q]*11)

    def test_shape_and_domain_guards(self):
        good = [law.Q] * 6
        with self.assertRaises(ValueError):
            law.derive_state(good[:5], good, "none")
        with self.assertRaises(TypeError):
            law.derive_state("1000000", good, "none")
        with self.assertRaises(TypeError):
            law.derive_state([True] + good[1:], good, "none")
        with self.assertRaises(TypeError):
            law.derive_state([1.0] + good[1:], good, "none")
        with self.assertRaises(ValueError):
            law.derive_state([-1] + good[1:], good, "none")
        with self.assertRaises(ValueError):
            law.derive_state(good, [-1] + good[1:], "none")
        with self.assertRaises(ValueError):
            law.derive_state(good, [law.Q+1] + good[1:], "none")
        with self.assertRaises(ValueError):
            law.compute_u_metric(good, good, [law.Q]*11)

    def test_i64_max_evidence_keeps_metric_intermediates_in_i128_domain(self):
        max_i64 = (1 << 63) - 1
        evidence = [max_i64] * 6
        density = [law.Q] * 6
        state = law.derive_state(evidence, density, "none")
        metric = law.compute_u_metric(evidence, density, state)
        self.assertEqual(metric, {
            "V_h": 55340232221134654842,
            "A_h": 553402322211346548,
            "delta": 55340232221122654842,
            "C": 999999,
            "u_raw": 1009998,
            "u_metric": 1000000,
        })

    def test_transform_allowlist_and_canonical_numeric_encoding(self):
        good = [law.Q] * 6
        for transform in ("rotate_d1_17", "rotate_d1_", "rotate_d1_015", "rotate_d1_٤٥", "unknown"):
            with self.subTest(transform=transform):
                with self.assertRaises(ValueError):
                    law.derive_state(good, good, transform)

    def test_audit_schema_order_unknown_fields_and_float_rejection(self):
        record = json.loads((ROOT / "golden_corpus.json").read_text(encoding="utf-8"))[0]["audit_record"]
        with self.assertRaises(ValueError):
            law.canonical_audit_bytes(dict(reversed(list(record.items()))))
        extra = dict(record)
        extra["unchecked"] = 1
        with self.assertRaises(ValueError):
            law.canonical_audit_bytes(extra)
        bad = dict(record)
        bad["u_metric"] = 0.1
        with self.assertRaises(TypeError):
            law.canonical_audit_bytes(bad)

if __name__ == "__main__":
    unittest.main(verbosity=2)

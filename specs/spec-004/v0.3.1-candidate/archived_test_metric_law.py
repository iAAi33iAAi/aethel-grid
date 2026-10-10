from spec004_v031_metric_law import derive_state, compute_u_metric, decision_from_u
import json, hashlib

corpus=json.load(open("golden_corpus.json", encoding="utf-8"))
assert len(corpus)==4
for v in corpus:
    r=v["audit_record"]
    state=derive_state(r["input_bundle"]["evidence"], r["input_bundle"]["density"], r["applied_transforms"][0])
    assert state==r["result_state"], v["id"]
    m=compute_u_metric(r["input_bundle"]["evidence"], r["input_bundle"]["density"], state)
    assert m["u_metric"]==r["u_metric"], (v["id"],m,r["u_metric"])
    assert decision_from_u(m["u_metric"])==r["decision"], v["id"]
    pre=json.dumps(r,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    assert pre==v["audit_preimage"], v["id"]
    assert hashlib.sha256(pre.encode()).hexdigest()==v["expected_sha256"], v["id"]
print("M4 v0.3.1 Python dynamic derivation: 4/4 PASS")

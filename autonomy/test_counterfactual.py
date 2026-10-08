def test_counterfactual_resolution_improves_score():
    baseline = {
        "readiness": {
            "canonical_conformance": 0.0,
            "proof_integrity": 1.0,
            "proof_graph": 1.0,
            "pfp_declared_completeness": 0.4,
        },
        "blockers": ["canonical-conformance"],
        "unresolved_invariants": [
            {"id":"INV-007","priority":"critical","gap":1.0},
            {"id":"INV-013","priority":"critical","gap":1.0},
        ],
    }
    from autonomy.counterfactual import Scenario, rank_scenarios
    result = rank_scenarios(
        baseline,
        (
            Scenario("do-nothing", {}, "baseline"),
            Scenario("canonical-ready", {"canonical_conformance": True}, "establish canonical conformance"),
        ),
    )
    assert result[0]["scenario_id"] == "canonical-ready"
    assert result[0]["delta"] > 0


def test_counterfactual_does_not_mutate_baseline():
    from autonomy.counterfactual import Scenario, scenario_score
    baseline = {
        "readiness": {"canonical_conformance": 0.0},
        "blockers": ["canonical-conformance"],
        "unresolved_invariants": [],
    }
    original = dict(baseline)
    scenario_score(baseline, Scenario("x", {"canonical_conformance": True}, "x"))
    assert baseline == original

from autonomy.multi_agent_provider import EndpointSpec, MultiAgentProposalProvider


class FakeProvider:
    def __init__(self, endpoint, model, api_key=None):
        self.endpoint = endpoint
        self.model = model

    def propose(self, snapshot):
        return [{"kind": "run_test", "target": ".", "risk": 0.1}]


def test_multi_agent_provider_normalizes_identity():
    provider = MultiAgentProposalProvider(
        (
            EndpointSpec(
                agent_id="a",
                endpoint="https://example.invalid/a",
                model="m-a",
                model_revision="rev-a",
                protocol="openai-compatible",
                agent_version="1",
                source_ref="git:a",
            ),
            EndpointSpec(
                agent_id="b",
                endpoint="https://example.invalid/b",
                model="m-b",
                model_revision="rev-b",
                protocol="openai-compatible",
                agent_version="1",
                source_ref="git:b",
            ),
        ),
        provider_factory=FakeProvider,
    )
    rows = provider.propose({"state": "x"})
    assert {row["agent_id"] for row in rows} == {"a", "b"}
    assert all(row["protocol"] == "openai-compatible" for row in rows)
    assert {row["model_revision"] for row in rows} == {"rev-a", "rev-b"}

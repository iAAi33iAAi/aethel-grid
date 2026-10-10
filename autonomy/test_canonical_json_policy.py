"""Cross-module canonical JSON invariants: valid JSON only, stable bytes."""
import math

import pytest

from conformance.contract import canonical_json as conformance_canonical_json
from autonomy.agent_attestation import canonical_json as attestation_canonical_json
from autonomy.agent_router import canonical_json as router_canonical_json
from autonomy.caios_runtime import canonical_json as runtime_canonical_json
from autonomy.evidence_bundle import canonical_json as bundle_canonical_json
from autonomy.evidence_ledger import canonical_json as ledger_canonical_json
from autonomy.proof_graph import canonical_json as proof_graph_canonical_json
from autonomy.proof_work_contract import canonical_json as work_contract_canonical_json
from federation.security_primitives import canonical_json as security_canonical_json
from federation.signed_envelope import canonical_json as signed_envelope_canonical_json
from integrations.remote_interop import canonical_json as remote_interop_canonical_json
from interop.aethel_service import canonical_json as aethel_service_canonical_json


SERIALIZERS = (
    ("conformance-contract", conformance_canonical_json),
    ("agent-attestation", attestation_canonical_json),
    ("agent-router", router_canonical_json),
    ("caios-runtime", runtime_canonical_json),
    ("evidence-bundle", bundle_canonical_json),
    ("evidence-ledger", ledger_canonical_json),
    ("proof-graph", proof_graph_canonical_json),
    ("proof-work-contract", work_contract_canonical_json),
    ("federation-security", security_canonical_json),
    ("signed-envelope", signed_envelope_canonical_json),
    ("remote-interop", remote_interop_canonical_json),
    ("aethel-interop-service", aethel_service_canonical_json),
)


@pytest.mark.parametrize("name,serializer", SERIALIZERS)
def test_canonical_json_keeps_existing_finite_encoding(name, serializer):
    value = {"z": "ok", "finite": 0.5, "n": 7}
    assert serializer(value) == b'{"finite":0.5,"n":7,"z":"ok"}'


@pytest.mark.parametrize("name,serializer", SERIALIZERS)
@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_nonfinite_numbers(name, serializer, nonfinite):
    with pytest.raises(ValueError):
        serializer({"nested": {"value": nonfinite}})

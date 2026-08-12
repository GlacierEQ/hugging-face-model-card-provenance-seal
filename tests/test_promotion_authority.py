"""Promotion behavior is bound to the expected provenance seal, not a sidecar authority layer."""
from model_card_provenance_seal import (
    Decision,
    ModelCardProvenanceSeal,
    ModelCardProvenanceSealRequest,
)


def _payload() -> dict:
    return {
        "model_id": "glaciereq/demo-model",
        "revision": "a" * 40,
        "artifacts": [{"path": "model.safetensors", "sha256": "b" * 64}],
        "card": {"license": "apache-2.0", "pipeline_tag": "text-generation"},
    }


def test_promotion_candidate_must_match_trusted_seal() -> None:
    engine = ModelCardProvenanceSeal()
    baseline = engine.evaluate(ModelCardProvenanceSealRequest("release", _payload(), budget=2.0))
    assert baseline.decision is Decision.ALLOW

    candidate = _payload()
    candidate["expected_seal"] = baseline.digest
    verified = engine.evaluate(ModelCardProvenanceSealRequest("release", candidate, budget=2.0))
    assert verified.decision is Decision.ALLOW

    candidate["artifacts"] = [{"path": "model.safetensors", "sha256": "c" * 64}]
    drifted = engine.evaluate(ModelCardProvenanceSealRequest("release", candidate, budget=2.0))
    assert drifted.decision is Decision.REFUSE
    assert "expected_seal_mismatch" in drifted.reasons
